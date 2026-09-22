#!/usr/bin/env bash
set -e

# Color helpers
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE} Himalaya Notification Installer       ${NC}"
echo -e "${BLUE}=======================================${NC}"
echo "Running prerequisite checks (no sudo required)..."
echo ""

# 1. Check Python 3
if ! command -v python3 >/dev/null 2>&1; then
    echo -e "${RED}[✗] Python 3 not found.${NC} Please install Python 3.8 or newer."
    exit 1
fi

PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)")
PY_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 8 ]; }; then
    echo -e "${RED}[✗] Python version $PY_VERSION is too old.${NC} Python 3.8+ required."
    exit 1
fi
echo -e "${GREEN}[✓] Python 3 found:${NC} Python $PY_VERSION"

# 2. Check himalaya
if ! command -v himalaya >/dev/null 2>&1; then
    echo -e "${RED}[✗] himalaya binary not found in PATH.${NC} Please install himalaya-cli."
    exit 1
fi
HIMALAYA_VER=$(himalaya --version 2>/dev/null | head -n 1)
echo -e "${GREEN}[✓] himalaya found:${NC} $HIMALAYA_VER"

# 3. Check himalaya accounts
ACCOUNTS_COUNT=$(python3 -c "import json, subprocess, sys; 
try:
    out = subprocess.check_output(['himalaya', '--quiet', '--output', 'json', 'account', 'list'], text=True, timeout=10)
    idx = out.find('[')
    if idx != -1:
        data = json.loads(out[idx:])
        print(len(data))
    else:
        print(0)
except Exception:
    print(0)" 2>/dev/null || echo 0)
if [ "$ACCOUNTS_COUNT" -eq 0 ]; then
    echo -e "${YELLOW}[!] Warning: No himalaya accounts detected.${NC} Please configure at least one account via himalaya."
else
    echo -e "${GREEN}[✓] himalaya accounts configured:${NC} $ACCOUNTS_COUNT account(s) detected"
fi

# 4. Check desktop notification support (notify-send or gdbus)
NOTIF_OK=0
if command -v notify-send >/dev/null 2>&1; then
    echo -e "${GREEN}[✓] Desktop notifications:${NC} notify-send available"
    NOTIF_OK=1
elif command -v gdbus >/dev/null 2>&1; then
    if gdbus call --session --dest org.freedesktop.Notifications --object-path /org/freedesktop/Notifications --method org.freedesktop.Notifications.GetServerInformation >/dev/null 2>&1; then
        echo -e "${GREEN}[✓] Desktop notifications:${NC} gdbus connected to FreeDesktop notification daemon"
        NOTIF_OK=1
    else
        echo -e "${YELLOW}[!] gdbus found, but DBus notification daemon not responding in current session.${NC}"
    fi
fi

if [ "$NOTIF_OK" -eq 0 ]; then
    echo -e "${YELLOW}[!] Warning: Neither notify-send nor active DBus notification server found.${NC}"
    echo "    Desktop popups may not display until a notification daemon is active."
fi

# 5. Check systemd user session
if ! command -v systemctl >/dev/null 2>&1; then
    echo -e "${RED}[✗] systemctl not found.${NC} systemd user service setup requires systemd."
    exit 1
fi

if ! systemctl --user status >/dev/null 2>&1; then
    echo -e "${RED}[✗] systemd --user manager is not responding.${NC} Ensure your user session is running."
    exit 1
fi
echo -e "${GREEN}[✓] systemd user manager:${NC} Active and responding"

echo ""
echo "All prerequisite checks passed!"
echo ""

# Determine absolute path to repo
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_PATH="$REPO_DIR/himalaya_notify.py"
chmod +x "$SCRIPT_PATH"

USER_SYSTEMD_DIR="$HOME/.config/systemd/user"
mkdir -p "$USER_SYSTEMD_DIR"

echo "Configuring systemd user units..."

# Replace {{SCRIPT_PATH}} and install service
sed "s|{{SCRIPT_PATH}}|$SCRIPT_PATH|g" "$REPO_DIR/systemd/himalaya-notification.service" > "$USER_SYSTEMD_DIR/himalaya-notification.service"

# Install timer
cp "$REPO_DIR/systemd/himalaya-notification.timer" "$USER_SYSTEMD_DIR/himalaya-notification.timer"

# Reload systemd user daemon and enable timer
systemctl --user daemon-reload
systemctl --user enable --now himalaya-notification.timer

echo -e "${GREEN}[✓] Service & timer successfully installed!${NC}"
echo ""
echo "Timer Schedule Status:"
systemctl --user list-timers himalaya-notification.timer --no-pager
echo ""
echo "You can manually test it anytime with:"
echo "  $SCRIPT_PATH check --dry-run"
echo "  $SCRIPT_PATH test-notify"
echo ""
echo "To uninstall, run:"
echo "  $REPO_DIR/uninstall.sh"
