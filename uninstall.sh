#!/usr/bin/env bash
set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE} Himalaya Notification Uninstaller     ${NC}"
echo -e "${BLUE}=======================================${NC}"

USER_SYSTEMD_DIR="$HOME/.config/systemd/user"

echo "Stopping and disabling systemd timer..."
systemctl --user stop himalaya-notification.timer 2>/dev/null || true
systemctl --user disable himalaya-notification.timer 2>/dev/null || true

echo "Removing user unit files..."
rm -f "$USER_SYSTEMD_DIR/himalaya-notification.service"
rm -f "$USER_SYSTEMD_DIR/himalaya-notification.timer"

systemctl --user daemon-reload

echo -e "${GREEN}[✓] Himalaya notification timer has been completely uninstalled.${NC}"
