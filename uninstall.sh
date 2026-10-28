#!/usr/bin/env bash
set -euo pipefail

APP_ID="linux-voice-assistant"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
rm -rf "$DATA_HOME/$APP_ID/app"
rm -f "$DATA_HOME/applications/$APP_ID.desktop"
rm -f "$DATA_HOME/icons/hicolor/scalable/apps/$APP_ID.svg"

DESKTOP_DIR=""
if command -v xdg-user-dir >/dev/null 2>&1; then
    DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
fi
if [ -z "$DESKTOP_DIR" ]; then
    if [ -d "$HOME/Masaüstü" ]; then
        DESKTOP_DIR="$HOME/Masaüstü"
    else
        DESKTOP_DIR="$HOME/Desktop"
    fi
fi
rm -f "$DESKTOP_DIR/Sesli Asistan.desktop"

echo "Uygulama kaldırıldı. İndirilen ses modeli korunuyor: $HOME/.local/share/$APP_ID/voices"
