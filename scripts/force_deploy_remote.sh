#!/usr/bin/env bash
set -euo pipefail

WHEEL_PATH="${1:-}"
REMOTE="${2:-}"
REMOTE_DIR="${3:-}"

if [ -z "$WHEEL_PATH" ] || [ -z "$REMOTE" ]; then
  echo "Usage: $0 <wheel-path> <remote> [remote-dir]"
  exit 1
fi

WHEEL_NAME=$(basename "$WHEEL_PATH")

echo "Cleaning remote /tmp..."
ssh "$REMOTE" 'rm -f /tmp/radioglobe-*.whl || true'

echo "Uploading $WHEEL_PATH to $REMOTE:/tmp/$WHEEL_NAME"
scp "$WHEEL_PATH" "$REMOTE:/tmp/$WHEEL_NAME"
scp stations/stations.json "$REMOTE:/tmp/stations.json" || true

# Require existing venv for force-deploy
if ! ssh "$REMOTE" '[ -f /opt/radioglobe/venv/bin/pip ]'; then
  echo "No venv found on remote at /opt/radioglobe/venv — refusing to do force-deploy. Run install.sh on the device or use 'make deploy' for a fresh install."
  exit 3
fi

echo "Installing wheel into existing venv (force reinstall)..."
ssh "$REMOTE" "/opt/radioglobe/venv/bin/pip install --upgrade --force-reinstall '/tmp/$WHEEL_NAME[pi]'"

# Ensure stations copied and VERSION written
ssh "$REMOTE" "mkdir -p /opt/radioglobe/stations || true; cp /tmp/stations.json /opt/radioglobe/stations/stations.json || true"

INSTALLED_VER=$(ssh "$REMOTE" '/opt/radioglobe/venv/bin/python -c "import importlib.metadata as m; print(m.version(\"radioglobe\"))"' 2>/dev/null || echo unknown)

ssh "$REMOTE" "echo \"$INSTALLED_VER\" > /opt/radioglobe/VERSION; echo RADIOGLOBE_VERSION=$INSTALLED_VER > /opt/radioglobe/version.env"

echo "Remote installed version: $INSTALLED_VER"

# Return success; caller will verify local vs remote
exit 0
