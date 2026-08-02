#!/usr/bin/env bash
set -e

RADIOGLOBE_USER=radioglobe
RADIOGLOBE_DIR=/opt/radioglobe
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "🚀 Installing RadioGlobe..."
echo "One-time system setup: OS deps, dtoverlay, sudoers, /opt/radioglobe"
echo "ownership, the service unit, and lingering. Needs sudo throughout."
echo "For routine code/data updates afterward, use update.sh instead —"
echo "it needs no sudo once this has run."

# -----------------------------
# Version: prefer VERSION injected by `make deploy` from the dev
# machine; fall back to `git describe` when running from a real
# clone on the target host (e.g. installed directly via git clone).
# -----------------------------
if [[ -f "$SRC_DIR/VERSION" ]]; then
    VERSION=$(cat "$SRC_DIR/VERSION")
elif [[ -d "$SRC_DIR/.git" ]]; then
    VERSION=$(git -C "$SRC_DIR" describe --tags --always --dirty 2>/dev/null || echo "unknown")
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
    rfkill \
    jq \
    swig \
    liblgpio-dev

# -----------------------------
# Rotary encoder dtoverlay (idempotent)
# -----------------------------
CONFIG_TXT=/boot/firmware/config.txt
# pin_a/pin_b (BCM 17/18, the dial's clock/direction lines) are the single
# source of truth for these pins — the kernel rotary-encoder driver reads
# them directly, no Python module owns or references them.
OVERLAY_LINE="dtoverlay=rotary-encoder,pin_a=17,pin_b=18,relative_axis=1"
if ! grep -qxF "$OVERLAY_LINE" "$CONFIG_TXT"; then
    echo "⚙️ Adding rotary-encoder dtoverlay to $CONFIG_TXT..."
    echo "$OVERLAY_LINE" | sudo tee -a "$CONFIG_TXT" > /dev/null
fi

# -----------------------------
# Ensure Bluetooth radio isn't soft-blocked (idempotent)
# Some images/imagers leave hci0 rfkill-blocked, which silently
# breaks Bluetooth speaker pairing until manually unblocked.
# systemd-rfkill saves this state on change and restores it on
# boot, so unblocking once here keeps it enabled across reboots.
# -----------------------------
if sudo rfkill list bluetooth | grep -q "Soft blocked: yes"; then
    echo "📶 Unblocking Bluetooth radio..."
    sudo rfkill unblock bluetooth
fi

# -----------------------------
# Allow passwordless poweroff (idempotent)
# The mid-button long-press shutdown handler runs `sudo poweroff`
# from radioglobe.service, which has no TTY to answer a password
# prompt. Some images grant the default user blanket NOPASSWD sudo;
# scope it to just poweroff here instead of relying on that.
# -----------------------------
SUDOERS_FILE=/etc/sudoers.d/radioglobe-poweroff
SUDOERS_LINE="$RADIOGLOBE_USER ALL=(root) NOPASSWD: /usr/sbin/poweroff"
if [[ ! -f "$SUDOERS_FILE" ]] || ! grep -qxF "$SUDOERS_LINE" "$SUDOERS_FILE"; then
    echo "🔑 Granting passwordless poweroff to $RADIOGLOBE_USER..."
    echo "$SUDOERS_LINE" | sudo tee "$SUDOERS_FILE.tmp" > /dev/null
    sudo visudo -c -f "$SUDOERS_FILE.tmp" > /dev/null
    sudo chmod 0440 "$SUDOERS_FILE.tmp"
    sudo mv "$SUDOERS_FILE.tmp" "$SUDOERS_FILE"
fi

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
# Ensure pip/setuptools/wheel are recent in the new venv, then install the project
sudo -u $RADIOGLOBE_USER \
    $RADIOGLOBE_DIR/venv/bin/python -m pip install --upgrade pip setuptools wheel

# Install the project into the venv (pyproject.toml points to src/).
# Prefer a built wheel in $SRC_DIR/dist if present (faster, reproducible), otherwise install from source.
if [ -d "$SRC_DIR/dist" ] && ls "$SRC_DIR/dist/radioglobe-"*.whl >/dev/null 2>&1; then
    WHEEL="$SRC_DIR/dist/$(ls "$SRC_DIR/dist/radioglobe-"*.whl | tail -n1 | xargs -n1 basename)"
    echo "📦 Installing wheel: $WHEEL"
    sudo -u $RADIOGLOBE_USER \
        $RADIOGLOBE_DIR/venv/bin/pip install "$WHEEL"
else
    echo "📦 Installing from source: $SRC_DIR"
    sudo -u $RADIOGLOBE_USER \
        $RADIOGLOBE_DIR/venv/bin/pip install "$SRC_DIR"
fi

# -----------------------------
# Stations + version (runtime data)
# -----------------------------
# The Python package is installed into the venv; runtime data such as stations
# and VERSION remain under $RADIOGLOBE_DIR so they can be edited/updated in-place.
sudo mkdir -p "$RADIOGLOBE_DIR/stations"
sudo cp "$SRC_DIR/stations/stations.json" "$RADIOGLOBE_DIR/stations/"
# Determine installed package version from the venv and write it for the service to display
INSTALLED_VER=$($RADIOGLOBE_DIR/venv/bin/python -c "import importlib.metadata as m; print(m.version('radioglobe'))" 2>/dev/null || echo "$VERSION")

echo "$INSTALLED_VER" | sudo tee "$RADIOGLOBE_DIR/VERSION" > /dev/null
echo "RADIOGLOBE_VERSION=$INSTALLED_VER" | sudo tee "$RADIOGLOBE_DIR/version.env" > /dev/null

sudo chown -R $RADIOGLOBE_USER:$RADIOGLOBE_USER $RADIOGLOBE_DIR

# -----------------------------
# Clean stations file
# -----------------------------
echo "🧹 Cleaning stations..."
sed -i 's/: NaN/: "No Name"/g' "$RADIOGLOBE_DIR/stations/stations.json"
sed -i -E 's#("url": *"[^"?]+)\?[^"]*"#\1"#g' "$RADIOGLOBE_DIR/stations/stations.json"
jq empty "$RADIOGLOBE_DIR/stations/stations.json"

# -----------------------------
# Install systemd user service
# -----------------------------
echo "⚙️ Installing service..."

SERVICE_FILE=/etc/systemd/user/radioglobe.service
sudo cp "$SRC_DIR/services/radioglobe.service" $SERVICE_FILE

sudo sed -i "s|__RADIOGLOBE_DIR__|$RADIOGLOBE_DIR|g" $SERVICE_FILE

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
