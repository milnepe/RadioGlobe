#!/usr/bin/env bash
set -e

RADIOGLOBE_USER=radioglobe
RADIOGLOBE_DIR=/opt/radioglobe
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "🚀 Installing RadioGlobe..."

# -----------------------------
# Read version (injected at build time)
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
# Install directory
# -----------------------------
echo "📁 Preparing install dir..."
sudo mkdir -p $RADIOGLOBE_DIR
sudo chown $RADIOGLOBE_USER:$RADIOGLOBE_USER $RADIOGLOBE_DIR

# -----------------------------
# Python venv
# -----------------------------
echo "🐍 Setting up virtualenv..."
python3 -m venv $RADIOGLOBE_DIR/venv
source $RADIOGLOBE_DIR/venv/bin/activate

pip install --upgrade pip
pip install -r "$SRC_DIR/requirements.txt"

# -----------------------------
# Copy application
# -----------------------------
echo "📂 Copying application..."
sudo rsync -a --delete \
    "$SRC_DIR/radioglobe/" \
    "$RADIOGLOBE_DIR/"

sudo cp "$SRC_DIR/stations/stations.json" "$RADIOGLOBE_DIR/"
sudo cp "$SRC_DIR/VERSION" "$RADIOGLOBE_DIR/VERSION"

sudo chown -R $RADIOGLOBE_USER:$RADIOGLOBE_USER $RADIOGLOBE_DIR

# -----------------------------
# Fix stations
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
# Enable lingering (CRITICAL)
# -----------------------------
echo "🔑 Enabling lingering..."
sudo loginctl enable-linger $RADIOGLOBE_USER

# -----------------------------
# Enable + start service
# -----------------------------
echo "🔄 Starting service..."

# runuser -l $RADIOGLOBE_USER -c "systemctl --user daemon-reload"
# runuser -l $RADIOGLOBE_USER -c "systemctl --user enable radioglobe.service"
# runuser -l $RADIOGLOBE_USER -c "systemctl --user restart radioglobe.service"
sudo -u $RADIOGLOBE_USER systemctl --user daemon-reload
sudo -u $RADIOGLOBE_USER systemctl --user enable radioglobe.service
sudo -u $RADIOGLOBE_USER systemctl --user restart radioglobe.service

echo "✅ Done!"
echo "📖 Logs: journalctl --user-unit=radioglobe.service -f"
