#!/usr/bin/env bash
set -e

RADIOGLOBE_DIR=/opt/radioglobe
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"

cd "$SRC_DIR"

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
echo "📂 Installing updated package into venv..."
# Reinstall the project into the existing venv. Prefer a built wheel in $SRC_DIR/dist if present.
if [ -d "$SRC_DIR/dist" ] && ls "$SRC_DIR/dist/radioglobe-"*.whl >/dev/null 2>&1; then
    WHEEL="$SRC_DIR/dist/$(ls "$SRC_DIR/dist/radioglobe-"*.whl | tail -n1 | xargs -n1 basename)"
    echo "📦 Installing wheel: $WHEEL"
    $RADIOGLOBE_DIR/venv/bin/pip install --upgrade "$SRC_DIR/dist/$WHEEL"
else
    echo "📦 Installing from source: $SRC_DIR"
    $RADIOGLOBE_DIR/venv/bin/pip install --upgrade "$SRC_DIR"
fi

# NOTE: unlike install.sh, this script does NOT sanitize stations.json
# (no NaN/query-string cleanup, no jq validation). Only run update.sh
# against a stations.json that's already clean — running it against a
# dirty one just ships the dirty data to the device again. Use install.sh
# if stations.json needs cleaning.
cp "$SRC_DIR/stations/stations.json" "$RADIOGLOBE_DIR/stations/"
# Capture the installed package version from the venv and write it for the service
INSTALLED_VER=$($RADIOGLOBE_DIR/venv/bin/python -c "import importlib.metadata as m; print(m.version('radioglobe'))" 2>/dev/null || echo "$VERSION")

echo "$INSTALLED_VER" > "$RADIOGLOBE_DIR/VERSION"
echo "RADIOGLOBE_VERSION=$INSTALLED_VER" > "$RADIOGLOBE_DIR/version.env"

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
