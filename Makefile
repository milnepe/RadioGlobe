SHELL := /bin/bash
APP_NAME=radioglobe
REMOTE=radioglobe@radioglobe.local
REMOTE_DIR=~/RadioGlobe

# Version is derived from git tags for developer builds
VERSION := $(shell git describe --tags --always --dirty 2>/dev/null || echo "0+dev")

.PHONY: version
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
	@VERSION=$$(git describe --tags --always --dirty 2>/dev/null || echo $(VERSION)); \
	echo $$VERSION > VERSION; \
	python -m pip install --upgrade build && python -m build --wheel --outdir dist; \
	echo "Version: $$VERSION"

# -----------------------------
# Deploy to device
# -----------------------------
deploy: build
	@echo "🚀 Deploying wheel to $(REMOTE)..."
	@WHEEL=$$(ls dist/radioglobe-*.whl 2>/dev/null | tail -n1) ; \
	if [ -z "$$WHEEL" ]; then echo "No wheel found in dist/; run 'make build' first"; exit 1; fi ; \
	echo "Uploading $$WHEEL to $(REMOTE):/tmp/" ; \
	scp "$$WHEEL" $(REMOTE):/tmp/ ; \
	scp stations/stations.json $(REMOTE):/tmp/stations.json || true ; \
	ssh $(REMOTE) "WHEEL=/tmp/$$(basename $$WHEEL); \
	if [ -f /opt/radioglobe/venv/bin/pip ]; then \
	    echo 'Installing wheel into existing venv...' ; \
	    /opt/radioglobe/venv/bin/pip install --no-deps --upgrade $$WHEEL || /opt/radioglobe/venv/bin/pip install --upgrade $$WHEEL ; \
	else \
	    echo 'No venv detected at /opt/radioglobe/venv — extract source and run install.sh on target' ; \
	    mkdir -p ~/RadioGlobe && exit 1 ; \
	fi ; \
	# Copy stations and write installed version
	mkdir -p /opt/radioglobe/stations || true ; \
	cp /tmp/stations.json /opt/radioglobe/stations/stations.json || true ; \
	INSTALLED_VER=$$(/opt/radioglobe/venv/bin/python -c 'import importlib.metadata as m; print(m.version("radioglobe"))' 2>/dev/null || echo unknown) ; \
	echo $$INSTALLED_VER > /opt/radioglobe/VERSION ; \
	echo "RADIOGLOBE_VERSION=$$INSTALLED_VER" > /opt/radioglobe/version.env ; \
	systemctl --user restart radioglobe.service || true"

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
