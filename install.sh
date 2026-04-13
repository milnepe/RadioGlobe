#!/usr/bin/env bash
set -e

RADIOGLOBE_USER=radioglobe
RADIOGLOBE_DIR=/opt/radioglobe
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "🚀 Installing RadioGlobe..."

# -----------------------------
# Version (injected from dev machine)
# -----------------------------
if [[ -f "$SRC_DIR/VERSION" ]]; then
    VERSION=$(cat "$SRC_DIR/VERSION")
else
    VERSION="unknown"
fi

echo "📦 Version: $VERSION"

# -----------------------------
# OS dependencies
# -----------------------------
echo "📦 Installing OS dependencies..."
sudo apt update
sudo apt install -y \
    vlc-bin \
    vlc-plugin-base \
    python3-venv \
    python3-dev \
    pulseaudio-module-bluetooth \
    jq

# -----------------------------
# Prepare install directory
# -----------------------------
echo "📁 Preparing install dir..."
sudo mkdir -p $RADIOGLOBE_DIR
sudo chown -R $RADIOGLOBE_USER:$RADIOGLOBE_USER $RADIOGLOBE_DIR

# -----------------------------
# Python virtual environment (idempotent)
# -----------------------------
if [ ! -f "$RADIOGLOBE_DIR/venv/bin/python" ]; then
    echo "🐍 Creating virtualenv..."
    sudo -u $RADIOGLOBE_USER python3 -m venv $RADIOGLOBE_DIR/venv
fi

echo "📦 Installing Python dependencies..."
sudo -u $RADIOGLOBE_USER \
    $RADIOGLOBE_DIR/venv/bin/pip install --upgrade pip

sudo -u $RADIOGLOBE_USER \
    $RADIOGLOBE_DIR/venv/bin/pip install -r "$SRC_DIR/requirements.txt"

# -----------------------------
# Copy application (SAFE: no delete)
# -----------------------------
echo "📂 Copying application..."
sudo cp -r "$SRC_DIR/radioglobe/"* "$RADIOGLOBE_DIR/"

# Stations + version
sudo cp "$SRC_DIR/stations/stations.json" "$RADIOGLOBE_DIR/"
sudo cp "$SRC_DIR/VERSION" "$RADIOGLOBE_DIR/VERSION"

sudo chown -R $RADIOGLOBE_USER:$RADIOGLOBE_USER $RADIOGLOBE_DIR

# -----------------------------
# Clean stations file
# -----------------------------
echo "🧹 Cleaning stations..."
sed -i 's/: NaN/: "No Name"/g' "$RADIOGLOBE_DIR/stations.json"
sed -i -E 's#("url": *"[^"?]+)\?[^"]*"#\1"#g' "$RADIOGLOBE_DIR/stations.json"
jq empty "$RADIOGLOBE_DIR/stations.json"

# -----------------------------
# Install systemd user service
# -----------------------------
echo "⚙️ Installing service..."

SERVICE_FILE=/etc/systemd/user/radioglobe.service
sudo cp "$SRC_DIR/services/radioglobe.service" $SERVICE_FILE

sudo sed -i "s|__RADIOGLOBE_DIR__|$RADIOGLOBE_DIR|g" $SERVICE_FILE
sudo sed -i "s|__VERSION__|$VERSION|g" $SERVICE_FILE

# -----------------------------
# Enable lingering (required for user services)
# -----------------------------
echo "🔑 Enabling lingering..."
sudo loginctl enable-linger $RADIOGLOBE_USER

# -----------------------------
# Enable service (DO NOT start here)
# -----------------------------
USER_ID=$(id -u $RADIOGLOBE_USER)
export XDG_RUNTIME_DIR=/run/user/$USER_ID

echo "🔄 Enabling service..."

sudo -u $RADIOGLOBE_USER \
    XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR \
    systemctl --user daemon-reload

sudo -u $RADIOGLOBE_USER \
    XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR \
    systemctl --user enable radioglobe.service

echo "✅ Installation complete!"
echo "⚠️ Reboot recommended to start service cleanly"
echo "📖 Logs after reboot:"
echo "   journalctl --user-unit=radioglobe.service -f"
