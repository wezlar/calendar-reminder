#!/usr/bin/env python3
"""Calendar Reminder - macOS Google Calendar alert daemon."""

import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCRIPT_DIR = Path(__file__).parent.resolve()
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def load_config() -> dict:
    config_file = SCRIPT_DIR / "config.json"
    defaults = {
        "filter_mode": "meet_only",
        "reminder_minutes": 1,
        "calendar_id": "primary",
        "poll_interval_seconds": 60,
        "fetch_interval_seconds": 3600,
        "credentials_file": "credentials.json",
        "token_file": "token.json",
    }
    if config_file.exists():
        with open(config_file) as f:
            return {**defaults, **json.load(f)}
    return defaults


def setup_logging() -> None:
    log_dir = Path.home() / "Library" / "Logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "calendar-reminder.log"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def get_calendar_service(config: dict):
    token_path = SCRIPT_DIR / config["token_file"]
    creds = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token_path.write_text(creds.to_json())
        else:
            logging.error(
                "No valid credentials. Run:  python3 calendar_reminder.py --auth"
            )
            sys.exit(1)

    return build("calendar", "v3", credentials=creds)


def is_meet_open_in_chrome(meet_url: str) -> bool:
    """Return True if a Chrome tab with this Google Meet is already open."""
    meet_path = urlparse(meet_url).path  # e.g. "/abc-defg-hij"
    if not meet_path or meet_path == "/":
        return False

    # Escape double quotes inside the path (shouldn't occur in Meet codes)
    safe_path = meet_path.replace('"', '\\"')
    script = f"""
set meetPath to "{safe_path}"
set foundTab to false
try
    tell application "Google Chrome"
        repeat with w in windows
            repeat with t in tabs of w
                if URL of t contains meetPath then
                    set foundTab to true
                end if
            end repeat
        end repeat
    end tell
end try
return foundTab
"""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() == "true"
    except Exception as exc:
        logging.warning("Chrome tab check failed: %s", exc)
        return False


def show_alert(summary: str, meet_url: str, minutes_away: float) -> None:
    """Show a non-blocking macOS alert dialog."""
    mins_int = max(0, int(minutes_away))
    if mins_int == 0:
        time_str = "is starting now"
    elif mins_int == 1:
        time_str = "starts in 1 minute"
    else:
        time_str = f"starts in {mins_int} minutes"

    # Escape single quotes for AppleScript
    safe_summary = summary.replace('"', '\\"')
    message = f"{safe_summary} {time_str}"

    if meet_url:
        safe_url = meet_url.replace('"', '\\"')
        script = f"""
set r to display alert "{safe_summary}" ¬
    message "{time_str}" ¬
    buttons {{"Dismiss", "Join"}} ¬
    default button "Join" ¬
    giving up after 300
if button returned of r is "Join" then
    open location "{safe_url}"
end if
"""
    else:
        script = f"""
display alert "{safe_summary}" ¬
    message "{time_str}" ¬
    buttons {{"Dismiss"}} ¬
    default button "Dismiss" ¬
    giving up after 300
"""

    subprocess.Popen(["osascript", "-e", script])
    logging.info("Alert shown: %s", message)


def fetch_todays_events(service, config: dict) -> list:
    """Fetch all events for the rest of today from the API. Called hourly."""
    now = datetime.now(timezone.utc)
    end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=0)
    events_result = (
        service.events()
        .list(
            calendarId=config["calendar_id"],
            timeMin=now.isoformat(),
            timeMax=end_of_day.isoformat(),
            singleEvents=True,
            orderBy="startTime",
            fields="items(id,summary,start,hangoutLink,status)",
        )
        .execute()
    )
    events = events_result.get("items", [])
    logging.info("Fetched %d event(s) from Google Calendar", len(events))
    return events


def check_and_alert(cached_events: list, config: dict, alerted_ids: set) -> None:
    """Check the cached event list and alert for anything starting soon. No API call."""
    now = datetime.now(timezone.utc)

    for event in cached_events:
        if event.get("status") == "cancelled":
            continue

        event_id = event.get("id")
        if not event_id or event_id in alerted_ids:
            continue

        start = event.get("start", {})
        # Skip all-day events (no dateTime, only date)
        if "dateTime" not in start:
            continue

        start_dt = datetime.fromisoformat(start["dateTime"])
        minutes_away = (start_dt - now).total_seconds() / 60

        if not (0 < minutes_away <= config["reminder_minutes"]):
            continue

        meet_url = event.get("hangoutLink", "")

        if config["filter_mode"] == "meet_only" and not meet_url:
            continue

        if meet_url and is_meet_open_in_chrome(meet_url):
            logging.info(
                "Suppressed '%s' - already open in Chrome", event.get("summary")
            )
            alerted_ids.add(event_id)
            continue

        show_alert(event.get("summary", "Meeting"), meet_url, minutes_away)
        alerted_ids.add(event_id)


def main_loop() -> None:
    setup_logging()
    config = load_config()
    service = get_calendar_service(config)
    alerted_ids: set = set()
    cached_events: list = []
    last_fetch_time: float = 0  # Force an immediate fetch on startup

    logging.info(
        "Calendar reminder started (filter_mode=%s, reminder_minutes=%s, fetch_interval=%ss)",
        config["filter_mode"],
        config["reminder_minutes"],
        config["fetch_interval_seconds"],
    )

    while True:
        try:
            config = load_config()  # Reload each cycle so edits take effect live

            # Re-fetch from the API on the fetch schedule (default: hourly)
            if time.monotonic() - last_fetch_time >= config["fetch_interval_seconds"]:
                cached_events = fetch_todays_events(service, config)
                last_fetch_time = time.monotonic()

            # Check the cache every poll cycle (default: every 60s) — no API call
            check_and_alert(cached_events, config, alerted_ids)

        except HttpError as exc:
            if exc.resp.status in (401, 403):
                logging.warning("Auth error %s, refreshing service", exc.resp.status)
                try:
                    service = get_calendar_service(config)
                    last_fetch_time = 0  # Force re-fetch after credential refresh
                except SystemExit:
                    raise
            else:
                logging.error("Calendar API error: %s", exc)
        except Exception as exc:
            logging.error("Unexpected error: %s", exc, exc_info=True)

        time.sleep(config.get("poll_interval_seconds", 60))


def auth_flow() -> None:
    """Interactive one-time OAuth flow. Run this manually before starting the daemon."""
    config = load_config()
    creds_path = SCRIPT_DIR / config["credentials_file"]
    token_path = SCRIPT_DIR / config["token_file"]

    if not creds_path.exists():
        print(f"Error: {creds_path} not found.")
        print("Download OAuth credentials from Google Cloud Console first.")
        sys.exit(1)

    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
    creds = flow.run_local_server(port=0)
    token_path.write_text(creds.to_json())
    print(f"Authentication successful. Token saved to {token_path}")


if __name__ == "__main__":
    if "--auth" in sys.argv:
        auth_flow()
    else:
        main_loop()
