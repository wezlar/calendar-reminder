#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"
PLIST_LABEL="local.calendar-reminder"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_LABEL.plist"
LOG_PATH="$HOME/Library/Logs/calendar-reminder.log"
PYTHON_BIN="$VENV_DIR/bin/python3"

echo ""
echo "=== Calendar Reminder Setup ==="
echo ""

# ── Step 1: Create virtual environment ──────────────────────────────────────
echo "→ Creating Python virtual environment..."
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r "$SCRIPT_DIR/requirements.txt"
echo "  Done."
echo ""

# ── Step 2: Google OAuth credentials ─────────────────────────────────────────
if [ ! -f "$SCRIPT_DIR/credentials.json" ]; then
    echo "=== Google OAuth Credentials Required ==="
    echo ""
    echo "You need to create OAuth 2.0 credentials in the Google Cloud Console."
    echo "Follow these steps:"
    echo ""
    echo "  1. Go to https://console.cloud.google.com/"
    echo "  2. Create a new project (or select an existing one)"
    echo "  3. Go to APIs & Services → Library"
    echo "     Search for 'Google Calendar API' and click Enable"
    echo "  4. Go to APIs & Services → Credentials"
    echo "     Click 'Create Credentials' → 'OAuth client ID'"
    echo "  5. Choose 'Desktop app' as the application type"
    echo "  6. Click Create, then Download JSON"
    echo "  7. Save the downloaded file as:"
    echo "     $SCRIPT_DIR/credentials.json"
    echo ""
    echo "  Note: On first use you may see a 'Google hasn't verified this app'"
    echo "  warning. Click 'Advanced' → 'Go to <app name> (unsafe)' to proceed."
    echo "  This is normal for personal OAuth apps."
    echo ""

    while [ ! -f "$SCRIPT_DIR/credentials.json" ]; do
        read -rp "Press Enter once credentials.json is in place (Ctrl+C to cancel)..."
        if [ ! -f "$SCRIPT_DIR/credentials.json" ]; then
            echo "  File not found yet, please check the path and try again."
        fi
    done
    echo ""
fi

# ── Step 3: Interactive OAuth flow ───────────────────────────────────────────
if [ ! -f "$SCRIPT_DIR/token.json" ]; then
    echo "→ Opening browser for Google Calendar authorization..."
    echo "  (A browser window will open — sign in and grant Calendar access)"
    echo ""
    "$PYTHON_BIN" "$SCRIPT_DIR/calendar_reminder.py" --auth
    echo ""
else
    echo "→ Existing token.json found, skipping auth flow."
    echo "  (Delete token.json and re-run setup.sh to re-authorize)"
    echo ""
fi

# ── Step 4: Install LaunchAgent ───────────────────────────────────────────────
echo "→ Installing LaunchAgent..."
mkdir -p "$HOME/Library/LaunchAgents"

cat > "$PLIST_PATH" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_BIN}</string>
        <string>${SCRIPT_DIR}/calendar_reminder.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${SCRIPT_DIR}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>LimitLoadToSessionType</key>
    <array>
        <string>Aqua</string>
    </array>
    <key>StandardOutPath</key>
    <string>${LOG_PATH}</string>
    <key>StandardErrorPath</key>
    <string>${LOG_PATH}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>${VENV_DIR}/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>HOME</key>
        <string>${HOME}</string>
    </dict>
</dict>
</plist>
PLIST

# Unload first in case it's already loaded (ignore errors)
launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"
echo "  Done."
echo ""

# ── Done ─────────────────────────────────────────────────────────────────────
echo "=== Setup Complete ==="
echo ""
echo "The calendar reminder is now running in the background."
echo "It will also start automatically when you log in."
echo ""
echo "Configuration: $SCRIPT_DIR/config.json"
echo "  filter_mode: 'meet_only' (only meetings with a Google Meet link)"
echo "               'all'       (every calendar event)"
echo "  reminder_minutes: minutes before the meeting to show the alert"
echo ""
echo "Logs:          $LOG_PATH"
echo ""
echo "To stop:       launchctl unload $PLIST_PATH"
echo "To start:      launchctl load $PLIST_PATH"
echo "To uninstall:  launchctl unload $PLIST_PATH && rm $PLIST_PATH"
echo ""
