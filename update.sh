#!/usr/bin/env bash
set -e

RADIOGLOBE_DIR=/opt/radioglobe
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "🚀 Updating RadioGlobe..."
echo "Safe for small code changes only — copies files and restarts the"
echo "service. Touches no system configuration (OS deps, dtoverlay,"
echo "sudoers, the service unit, lingering) and needs no sudo — run"
echo "install.sh instead for first-time setup or if any of that changed."

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
# Copy application (SAFE: no delete)
# $RADIOGLOBE_DIR is owned by the radioglobe user (set up once by
# install.sh), so a plain cp works here with no sudo — this script is
# meant to run entirely as the radioglobe user over SSH.
# -----------------------------
echo "📂 Copying application..."
cp -r "$SRC_DIR/radioglobe" "$RADIOGLOBE_DIR/"

# NOTE: unlike install.sh, this script does NOT sanitize stations.json
# (no NaN/query-string cleanup, no jq validation). Only run update.sh
# against a stations.json that's already clean — running it against a
# dirty one just ships the dirty data to the device again. Use install.sh
# if stations.json needs cleaning.
cp "$SRC_DIR/stations/stations.json" "$RADIOGLOBE_DIR/stations/"
cp "$SRC_DIR/VERSION" "$RADIOGLOBE_DIR/VERSION"
echo "RADIOGLOBE_VERSION=$VERSION" > "$RADIOGLOBE_DIR/version.env"

# -----------------------------
# Restart the service to pick up the new code
#
# version.env is an EnvironmentFile= referenced by the (sudo-only) unit
# file, not the unit file itself — systemd re-reads it fresh on every
# service start, so a plain restart is enough to pick up the new version
# banner. No daemon-reload needed; that's only for unit-file changes.
# -----------------------------
echo "🔄 Restarting service..."
systemctl --user restart radioglobe.service

echo "✅ Update complete — running $VERSION"
echo "📖 Logs: journalctl --user-unit=radioglobe.service -f"
