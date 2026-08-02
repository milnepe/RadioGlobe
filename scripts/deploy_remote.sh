#!/usr/bin/env bash
set -euo pipefail

WHEEL_PATH="$1"
REMOTE="$2"
REMOTE_DIR="$3"

WHEEL_NAME=$(basename "$WHEEL_PATH")

echo "Cleaning remote /tmp..."
ssh "$REMOTE" 'rm -f /tmp/radioglobe-*.whl || true'

echo "Uploading $WHEEL_PATH to $REMOTE:/tmp/$WHEEL_NAME"
scp "$WHEEL_PATH" "$REMOTE:/tmp/$WHEEL_NAME"
scp stations/stations.json "$REMOTE:/tmp/stations.json" || true

# If venv exists, install into it; otherwise rsync and run install.sh on remote
if ssh "$REMOTE" '[ -f /opt/radioglobe/venv/bin/pip ]'; then
    echo "Installing wheel into existing venv on $REMOTE..."
    ssh "$REMOTE" "/opt/radioglobe/venv/bin/pip install --upgrade /tmp/$WHEEL_NAME"
    ssh "$REMOTE" "mkdir -p /opt/radioglobe/stations || true; cp /tmp/stations.json /opt/radioglobe/stations/stations.json || true"
    INSTALLED_VER=$(ssh "$REMOTE" '/opt/radioglobe/venv/bin/python -c "import importlib.metadata as m; print(m.version(\"radioglobe\"))"' 2>/dev/null || echo unknown)
    ssh "$REMOTE" "echo \"$INSTALLED_VER\" > /opt/radioglobe/VERSION; echo RADIOGLOBE_VERSION=$INSTALLED_VER > /opt/radioglobe/version.env; systemctl --user restart radioglobe.service || true"
else
    echo "No venv found on device; falling back to rsync+install.sh (interactive)"
    rsync -av --delete \
        --exclude ".git" \
        --exclude "__pycache__" \
        --exclude "*.pyc" \
        --exclude ".venv" \
        --exclude ".pytest_cache" \
        --exclude ".ruff_cache" \
        --exclude ".claude" \
        --exclude ".python-version" \
        --exclude ".lgd-nfy0" \
        ./ "$REMOTE:$REMOTE_DIR/"
    ssh "$REMOTE" "cd $REMOTE_DIR && ./install.sh"
fi
