SHELL := /bin/bash
APP_NAME=radioglobe
REMOTE=radioglobe@radioglobe.local
REMOTE_DIR=~/RadioGlobe

# Version is derived from git tags for developer builds
VERSION := $(shell git describe --tags --always --dirty 2>/dev/null || echo "0+dev")

.PHONY: version build deploy update install release clean device-version

version:
	@echo $(VERSION)

# -----------------------------
# Version bumping
# -----------------------------
bump-patch:
	@awk -F. '{printf "%d.%d.%d", $$1, $$2, $$3+1}' <<< "$(VERSION)" > .new_version
	@$(MAKE) set-version

bump-minor:
	@awk -F. '{printf "%d.%d.%d", $$1, $$2+1, 0}' <<< "$(VERSION)" > .new_version
	@$(MAKE) set-version

bump-major:
	@awk -F. '{printf "%d.%d.%d", $$1+1, 0, 0}' <<< "$(VERSION)" > .new_version
	@$(MAKE) set-version

set-version:
	@NEW_VERSION=$$(cat .new_version); \
	echo $$NEW_VERSION > VERSION; \
	sed -i "s/^version = \".*\"/version = \"$$NEW_VERSION\"/" $(VERSION_FILE); \
	rm .new_version; \
	git add VERSION $(VERSION_FILE); \
	git commit -m "Release v$$NEW_VERSION"; \
	git tag v$$NEW_VERSION

# -----------------------------
# Build (inject git info)
# -----------------------------
build:
	@echo "📦 Building version..."
	@python -m pip install --upgrade build setuptools_scm >/dev/null; \
	# Ensure old build artifacts don't make 'make' consider the target up-to-date
	rm -rf dist build || true; \
	VERSION=$$(python -c "from setuptools_scm import get_version; print(get_version())"); \
	echo $$VERSION > VERSION; \
	python -m build --wheel --outdir dist; \
	echo "Version: $$VERSION"

# -----------------------------
# Deploy to device
# -----------------------------
deploy: build
	@echo "🚀 Deploying wheel to $(REMOTE)..."
	@WHEEL=$$(ls dist/radioglobe-*.whl 2>/dev/null | tail -n1) ; \
	if [ -z "$$WHEEL" ]; then echo "No wheel found in dist/; run 'make build' first"; exit 1; fi ; \
	WHEEL_NAME=$$(basename "$$WHEEL") ; \
	echo "Uploading $$WHEEL to $(REMOTE):/tmp/$$WHEEL_NAME" ; \
	scp "$$WHEEL" $(REMOTE):/tmp/$$WHEEL_NAME ; \
	scp stations/stations.json $(REMOTE):/tmp/stations.json || true ; \
	# If a venv exists on the device, install into it. Otherwise rsync the repo and run install.sh on the remote.
	ssh $(REMOTE) 'if [ -f /opt/radioglobe/venv/bin/pip ]; then exit 0; else exit 1; fi' && \
	ssh $(REMOTE) "echo 'Installing wheel into existing venv...' ; \
	    /opt/radioglobe/venv/bin/pip install --upgrade /tmp/$$WHEEL_NAME ; \
	    mkdir -p /opt/radioglobe/stations || true ; \
	    cp /tmp/stations.json /opt/radioglobe/stations/stations.json || true ; \
	    INSTALLED_VER=$$(/opt/radioglobe/venv/bin/python -c 'import importlib.metadata as m; print(m.version("radioglobe"))' 2>/dev/null || echo unknown) ; \
	    echo $$INSTALLED_VER > /opt/radioglobe/VERSION ; \
	    echo "RADIOGLOBE_VERSION=$$INSTALLED_VER" > /opt/radioglobe/version.env ; \
	    systemctl --user restart radioglobe.service || true" || \
	(rsync -av --delete \
		--exclude ".git" \
		--exclude "__pycache__" \
		--exclude "*.pyc" \
		--exclude ".venv" \
		--exclude ".pytest_cache" \
		--exclude ".ruff_cache" \
		--exclude ".claude" \
		--exclude ".python-version" \
		--exclude ".lgd-nfy0" \
		./ $(REMOTE):$(REMOTE_DIR)/ && ssh $(REMOTE) "cd $(REMOTE_DIR) && ./install.sh")

# -----------------------------
# Force deploy (reinstall wheel and verify installed version)
# -----------------------------
force-deploy: build
	@echo "🚀 Force deploying wheel to $(REMOTE)..."
	@WHEEL=$$(ls dist/radioglobe-*.whl 2>/dev/null | tail -n1) ; \
	if [ -z "$$WHEEL" ]; then echo "No wheel found in dist/; run 'make build' first"; exit 1; fi ; \
	WHEEL_NAME=$$(basename "$$WHEEL") ; \
	echo "Uploading $$WHEEL to $(REMOTE):/tmp/$$WHEEL_NAME" ; \
	scp "$$WHEEL" $(REMOTE):/tmp/$$WHEEL_NAME ; \
	scp stations/stations.json $(REMOTE):/tmp/stations.json || true ; \
	# Install wheel into venv with force-reinstall if venv exists; otherwise rsync+install.sh
	ssh $(REMOTE) 'if [ -f /opt/radioglobe/venv/bin/pip ]; then exit 0; else exit 1; fi' && \
	ssh $(REMOTE) "echo 'Installing wheel into existing venv (force reinstall)...' ; /opt/radioglobe/venv/bin/pip install --upgrade --force-reinstall /tmp/$$WHEEL_NAME ; mkdir -p /opt/radioglobe/stations || true ; cp /tmp/stations.json /opt/radioglobe/stations/stations.json || true ; /bin/sh -lc '\''INSTALLED_VER=$$((/opt/radioglobe/venv/bin/python -c "import importlib.metadata as m; print(m.version(\\\"radioglobe\\\"))") 2>/dev/null || echo unknown); echo $$INSTALLED_VER > /opt/radioglobe/VERSION; echo "RADIOGLOBE_VERSION=$$INSTALLED_VER" > /opt/radioglobe/version.env'\''" || \
	(echo "No venv found on remote at /opt/radioglobe/venv — aborting force-deploy. Run install.sh on the device or use 'make deploy' for a fresh install."; exit 3) ; \
	# Fetch installed version and compare
	REMOTE_VER=$$(ssh $(REMOTE) 'cat /opt/radioglobe/VERSION 2>/dev/null || /opt/radioglobe/venv/bin/python -c "import importlib.metadata as m; print(m.version(\"radioglobe\"))"') ; \
	LOCAL_VER=$$(cat VERSION 2>/dev/null || echo unknown) ; \
	echo "Local version: $$LOCAL_VER" ; \
	echo "Remote version: $$REMOTE_VER" ; \
	if [ "$$LOCAL_VER" != "$$REMOTE_VER" ]; then echo "Version mismatch: local ($$LOCAL_VER) != remote ($$REMOTE_VER)"; exit 2; fi ; \
	echo "✅ Force deploy succeeded: versions match ($$LOCAL_VER)"

# -----------------------------
# Update on device
# -----------------------------
update:
	ssh $(REMOTE) "cd $(REMOTE_DIR) && ./update.sh"

# -----------------------------
# Install on device
# -----------------------------
install:
	ssh -t $(REMOTE) "cd $(REMOTE_DIR) && ./install.sh"

# -----------------------------
# Full release
# -----------------------------
release: bump-patch deploy install
	@git push
	@git push --tags

# -----------------------------
# Remove version file
# -----------------------------
clean:
	rm -f VERSION

# -----------------------------
# Check version on device
# -----------------------------
device-version:
	@echo "Device version:"
	@ssh $(REMOTE) "cd $(REMOTE_DIR) && cat VERSION"
