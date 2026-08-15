SHELL := /bin/bash
APP_NAME=radioglobe
REMOTE=radioglobe@radioglobe.local
REMOTE_DIR=~/RadioGlobe

# Version is derived from git tags for developer builds
VERSION := $(shell git describe --tags --always --dirty 2>/dev/null || echo "0+dev")

.PHONY: version build deploy update install release clean device-version force-deploy

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
	rm .new_version; \
	git add VERSION; \
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
	@echo "🚀 Deploying wheel to $(REMOTE)..."; \
	WHEEL_PATH=$$(ls dist/radioglobe-*.whl 2>/dev/null | tail -n1) ; \
	if [ -z "$$WHEEL_PATH" ]; then echo "No wheel found in dist/; run 'make build' first"; exit 1; fi ; \
	./scripts/deploy_remote.sh "$$WHEEL_PATH" $(REMOTE) $(REMOTE_DIR)

# -----------------------------
# Force deploy (reinstall wheel and verify installed version)
# -----------------------------
force-deploy: build
	@echo "🚀 Force deploying wheel to $(REMOTE)..."; \
	WHEEL_PATH=$$(ls dist/radioglobe-*.whl 2>/dev/null | tail -n1) ; \
	if [ -z "$$WHEEL_PATH" ]; then echo "No wheel found in dist/; run 'make build' first"; exit 1; fi ; \
	./scripts/force_deploy_remote.sh "$$WHEEL_PATH" $(REMOTE) $(REMOTE_DIR) ; \
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
	@echo -n "Device version: "
	@ssh $(REMOTE) 'cat /opt/radioglobe/VERSION 2>/dev/null || /opt/radioglobe/venv/bin/python -c "import importlib.metadata as m; print(m.version(\"radioglobe\"))"'
