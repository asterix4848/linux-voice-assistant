#!/usr/bin/env bash
set -euo pipefail

APP_ID="linux-voice-assistant"
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
APP_HOME="$DATA_HOME/$APP_ID"
APP_DIR="$APP_HOME/app"
APPLICATIONS_DIR="$DATA_HOME/applications"
ICON_DIR="$DATA_HOME/icons/hicolor/scalable/apps"

if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 bulunamadı. Önce Linux Mint'te Python 3 kur." >&2
    exit 1
fi

if ! python3 -c 'import tkinter' >/dev/null 2>&1; then
    echo "Tkinter bulunamadı. Terminalde şu komutu çalıştır: sudo apt install python3-tk" >&2
    exit 1
fi

if ! python3 -m venv --help >/dev/null 2>&1; then
    echo "Python sanal ortam desteği bulunamadı. Terminalde şu komutu çalıştır: sudo apt install python3-venv" >&2
    exit 1
fi

if ! command -v pw-record >/dev/null 2>&1; then
    echo "PipeWire kayıt aracı bulunamadı. Terminalde şu komutu çalıştır: sudo apt install pipewire-bin" >&2
    exit 1
fi

mkdir -p "$APP_DIR" "$APPLICATIONS_DIR" "$ICON_DIR"
cp "$SOURCE_DIR/app.py" "$SOURCE_DIR/requirements.txt" "$SOURCE_DIR/LICENSE" "$APP_DIR/"
cp "$SOURCE_DIR/linux-voice-assistant.svg" "$ICON_DIR/$APP_ID.svg"

if [ ! -x "$APP_DIR/.venv/bin/python" ]; then
    python3 -m venv "$APP_DIR/.venv"
fi

"$APP_DIR/.venv/bin/python" -m pip install --upgrade pip
"$APP_DIR/.venv/bin/python" -m pip install -r "$APP_DIR/requirements.txt"

cat > "$APP_DIR/launch.sh" <<EOF
#!/usr/bin/env bash
APP_DIR="$APP_DIR"
cd "\$APP_DIR"
exec "\$APP_DIR/.venv/bin/python" "\$APP_DIR/app.py"
EOF
chmod +x "$APP_DIR/launch.sh"

cat > "$APPLICATIONS_DIR/$APP_ID.desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Sesli Asistan
Comment=Türkçe sesli komut asistanı
Exec="$APP_DIR/launch.sh"
TryExec=$APP_DIR/launch.sh
Icon=$APP_ID
Terminal=false
Categories=Utility;AudioVideo;
StartupNotify=true
EOF
chmod +x "$APPLICATIONS_DIR/$APP_ID.desktop"

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
mkdir -p "$DESKTOP_DIR"
cp "$APPLICATIONS_DIR/$APP_ID.desktop" "$DESKTOP_DIR/Sesli Asistan.desktop"
chmod +x "$DESKTOP_DIR/Sesli Asistan.desktop"
if command -v gio >/dev/null 2>&1; then
    gio set "$DESKTOP_DIR/Sesli Asistan.desktop" metadata::trusted true 2>/dev/null || true
fi

echo "Kurulum tamamlandı. Sesli Asistan masaüstüne ve uygulama menüsüne eklendi."
echo "İlk açılışta konuşma tanıma ve Türkçe ses modellerinin indirilmesi gerekebilir."
