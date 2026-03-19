# Calendar Reminder

A macOS background app that watches your Google Calendar and pops up an alert before your meetings start. It runs silently in the background and restarts automatically when you log in.

## Features

- Native macOS alert dialog with a **Join** button for Google Meet meetings
- Filter to only meetings that have a Google Meet link, or alert for all events
- Suppresses the alert if you already have the Google Meet open in a Chrome tab
- Reloads your configuration live — no restart needed after editing `config.json`

## Prerequisites

- macOS
- Python 3 (comes with macOS — check with `python3 --version` in Terminal)
- A Google account with Google Calendar

## Setup

### Step 1 — Make the setup script executable

Open Terminal, navigate to this folder, and run:

```bash
cd ~/development/calendar-reminder
chmod +x setup.sh
```

### Step 2 — Get the `credentials.json` file

The app uses Google OAuth to read your calendar. `credentials.json` identifies the app to Google — **one person sets this up once and shares the file with everyone else.** If someone in your team has already done this, skip to Step 3.

#### If you are setting this up for the first time (product owner step)

1. Go to [https://console.cloud.google.com/](https://console.cloud.google.com/)
2. Click the project dropdown at the top and choose **New Project**. Give it any name (e.g. "Calendar Reminder") and click **Create**
3. In the left sidebar go to **APIs & Services → Library**. Search for **Google Calendar API** and click **Enable**
4. Go to **APIs & Services → OAuth consent screen**

   **If your company uses Google Workspace:** Choose **Internal**. This restricts the app to your organisation only and means colleagues will not see any security warning when they sign in. Skip the "Test users" step below.

   **If you are not on Google Workspace:** Choose **External**. Fill in any app name and save. Then go to the **Test users** section and add the Google accounts of everyone who will use the app (up to 100). This removes the security warning for listed users.

5. Go to **APIs & Services → Credentials**. Click **Create Credentials → OAuth client ID**
6. Choose **Desktop app** as the application type and click **Create**
7. Click **Download JSON** on the confirmation popup
8. Rename the downloaded file to `credentials.json`
9. Add it to the project folder and commit it to your repo, or share it with your team directly. It is safe to share — it only identifies the app, not any individual user's account.

#### If someone has already set this up

Place the shared `credentials.json` file into this project folder:

```
~/development/calendar-reminder/credentials.json
```

### Step 3 — Run setup

```bash
./setup.sh
```

The script will:

1. Create a Python virtual environment — an isolated copy of Python with all the required packages installed inside this project folder, so nothing on the rest of your Mac is affected
2. Ask you to confirm `credentials.json` is in place
3. Open a browser window for a one-time Google sign-in — **every person signs in with their own Google account** so the app can read their own calendar. This produces a `token.json` file that stays on your machine and is never shared
4. Install the app as a **LaunchAgent** — a background process that starts automatically every time you log in

> **"Google hasn't verified this app" warning:** If you see this, it means you are either not on Google Workspace, or the product owner has not yet added you as a test user. Ask them to add your Google account under **OAuth consent screen → Test users** in the Cloud Console. If they have done this, click **Advanced → Go to \<app name\> (unsafe)** to proceed — it is safe for an internal app.

After setup completes the reminder is running immediately.

---

## Configuration

Edit `config.json` to change the behaviour. Changes take effect on the next poll (within 60 seconds) — no restart needed.

```json
{
  "filter_mode": "meet_only",
  "reminder_minutes": 1,
  "calendar_id": "primary",
  "poll_interval_seconds": 60,
  "fetch_interval_seconds": 3600,
  "credentials_file": "credentials.json",
  "token_file": "token.json"
}
```

| Key                      | Description                                                         | Options / Default                                                    |
| ------------------------ | ------------------------------------------------------------------- | -------------------------------------------------------------------- |
| `filter_mode`            | Which meetings to alert for                                         | `"meet_only"` (Google Meet only) or `"all"` (every event)            |
| `reminder_minutes`       | How many minutes before the meeting to show the alert               | Any number — default `1`                                             |
| `calendar_id`            | Which calendar to watch                                             | `"primary"` for your main calendar, or a full calendar email address |
| `fetch_interval_seconds` | How often to call the Google Calendar API to refresh the event list | Default `3600` (once per hour)                                       |
| `poll_interval_seconds`  | How often to check the cached event list for upcoming meetings      | Default `60` (every minute)                                          |

The app fetches your full day of events from Google once per hour and stores them locally. The every-60-second check looks at that local cache — it does not call Google each time. This means the app makes around 10–15 API calls per day rather than 1,440.

> **Note:** Because events are cached hourly, a meeting added to your calendar less than an hour before it starts may not trigger an alert. If this is a concern, lower `fetch_interval_seconds` to `900` (every 15 minutes) — still only ~100 API calls per day.

---

## Stopping and removing the app

### Temporarily stop

This stops the reminder without uninstalling it. It will start again the next time you log in.

```bash
launchctl unload ~/Library/LaunchAgents/local.calendar-reminder.plist
```

To start it again without logging out:

```bash
launchctl load ~/Library/LaunchAgents/local.calendar-reminder.plist
```

### Fully uninstall

Run these three commands in order. Each one is safe to run even if the previous step was already done.

**1. Stop and remove the background process:**

```bash
launchctl unload ~/Library/LaunchAgents/local.calendar-reminder.plist
rm ~/Library/LaunchAgents/local.calendar-reminder.plist
```

**2. Delete the project folder:**

```bash
rm -rf ~/development/calendar-reminder
```

**3. Revoke Google Calendar access (optional but recommended):**

Go to [https://myaccount.google.com/permissions](https://myaccount.google.com/permissions), find the app by the name you gave it during setup, and click **Remove Access**. This stops the app from being able to access your calendar even if any files were missed above.

## Logs

If something isn't working, check the log file:

```bash
tail -f ~/Library/Logs/calendar-reminder.log
```

## Re-authorizing Google

If you ever revoke access or get an authentication error, delete `token.json` and run setup again:

```bash
rm ~/development/calendar-reminder/token.json
./setup.sh
```
