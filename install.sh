#!/usr/bin/env bash
set -e

RADIOGLOBE_USER=radioglobe
RADIOGLOBE_DIR=/opt/radioglobe
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"

cd "$SRC_DIR"

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
    jq

# -----------------------------
# Rotary encoder dtoverlay (idempotent)
# -----------------------------
CONFIG_TXT=/boot/firmware/config.txt
# pin_a/pin_b (BCM 18/17, the dial's two quadrature switch outputs — not a
# clock/direction pair) are the single source of truth for these pins — the
# kernel rotary-encoder driver reads them directly, no Python module owns
# or references them.
OVERLAY_LINE="dtoverlay=rotary-encoder,pin_a=18,pin_b=17,relative_axis=1"
if ! grep -qxF "$OVERLAY_LINE" "$CONFIG_TXT"; then
    echo "⚙️ Adding rotary-encoder dtoverlay to $CONFIG_TXT..."
    echo "$OVERLAY_LINE" | sudo tee -a "$CONFIG_TXT" > /dev/null
fi

# -----------------------------
# Button dtoverlays (idempotent)
# -----------------------------
# Each button is read via the kernel gpio-keys driver instead of RPi.GPIO.
# keycode= values must match buttons.py's _KEYCODE_BTN_* constants exactly
# (256/257/258/259 = evdev.ecodes.BTN_0..BTN_3) - device discovery there
# matches on keycode, not on the label= param below (confirmed on-device
# that label doesn't reliably set the evdev device name).
BUTTON_OVERLAY_LINES=(
    "dtoverlay=gpio-key,gpio=27,gpio_pull=up,label=jog,keycode=256"
    "dtoverlay=gpio-key,gpio=5,gpio_pull=up,label=top,keycode=257"
    "dtoverlay=gpio-key,gpio=6,gpio_pull=up,label=mid,keycode=258"
    "dtoverlay=gpio-key,gpio=12,gpio_pull=up,label=bottom,keycode=259"
)
for line in "${BUTTON_OVERLAY_LINES[@]}"; do
    if ! grep -qxF "$line" "$CONFIG_TXT"; then
        echo "⚙️ Adding button dtoverlay to $CONFIG_TXT: $line"
        echo "$line" | sudo tee -a "$CONFIG_TXT" > /dev/null
    fi
done

# -----------------------------
# RGB LED dtoverlays (idempotent)
# -----------------------------
# The RGB status LED is driven via the kernel gpio-led (leds-gpio) driver
# instead of RPi.GPIO. label= values must match rgb_led.py's
# _LED_LABEL_RED/_GREEN/_BLUE constants exactly - unlike gpio-key, gpio-led's
# label= was confirmed on-device to reliably set the sysfs device name
# (/sys/class/leds/<label>/brightness), so no keycode-style workaround is
# needed here.
LED_OVERLAY_LINES=(
    "dtoverlay=gpio-led,gpio=22,label=led-red"
    "dtoverlay=gpio-led,gpio=23,label=led-green"
    "dtoverlay=gpio-led,gpio=24,label=led-blue"
)
for line in "${LED_OVERLAY_LINES[@]}"; do
    if ! grep -qxF "$line" "$CONFIG_TXT"; then
        echo "⚙️ Adding LED dtoverlay to $CONFIG_TXT: $line"
        echo "$line" | sudo tee -a "$CONFIG_TXT" > /dev/null
    fi
done

# -----------------------------
# LED sysfs udev rule (idempotent)
# -----------------------------
# /sys/class/leds/*/brightness is root:root mode 644 by default - unlike
# /dev/input/* (readable via the `input` group), nothing grants a
# non-root user write access. $RADIOGLOBE_USER is already in the `gpio`
# group (used for GPIO character device access), so reuse it here rather
# than inventing a new group.
UDEV_RULES_FILE=/etc/udev/rules.d/99-radioglobe-leds.rules
UDEV_RULES_CONTENT='SUBSYSTEM=="leds", KERNEL=="led-red", RUN+="/bin/chgrp gpio /sys%p/brightness", RUN+="/bin/chmod g+w /sys%p/brightness"
SUBSYSTEM=="leds", KERNEL=="led-green", RUN+="/bin/chgrp gpio /sys%p/brightness", RUN+="/bin/chmod g+w /sys%p/brightness"
SUBSYSTEM=="leds", KERNEL=="led-blue", RUN+="/bin/chgrp gpio /sys%p/brightness", RUN+="/bin/chmod g+w /sys%p/brightness"'
if [[ ! -f "$UDEV_RULES_FILE" ]] || ! diff -q <(echo "$UDEV_RULES_CONTENT") "$UDEV_RULES_FILE" > /dev/null 2>&1; then
    echo "🔑 Installing udev rule for LED sysfs access..."
    echo "$UDEV_RULES_CONTENT" | sudo tee "$UDEV_RULES_FILE" > /dev/null
    sudo udevadm control --reload-rules
    # Re-applies to LEDs that already exist from a prior boot (e.g. re-running
    # install.sh after upgrading) - a no-op if the overlay hasn't loaded yet,
    # which still needs the reboot below regardless.
    sudo udevadm trigger --subsystem-match=leds || true
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
        $RADIOGLOBE_DIR/venv/bin/pip install "$WHEEL[pi]"
else
    echo "📦 Installing from source: $SRC_DIR"
    sudo -u $RADIOGLOBE_USER \
        $RADIOGLOBE_DIR/venv/bin/pip install "$SRC_DIR[pi]"
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
