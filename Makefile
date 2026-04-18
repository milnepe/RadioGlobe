SHELL := /bin/bash
APP_NAME=radioglobe
REMOTE=radioglobe@radioglobe.local
REMOTE_DIR=~/RadioGlobe

VERSION_FILE=pyproject.toml

VERSION=$(shell grep '^version' $(VERSION_FILE) | cut -d '"' -f2)

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
	echo "Version: $$VERSION"

# -----------------------------
# Deploy to device
# -----------------------------
deploy: build
	@echo "🚀 Deploying to $(REMOTE)..."
	rsync -av --delete \
		--exclude ".git" \
		--exclude "__pycache__" \
		--exclude "*.pyc" \
		./ $(REMOTE):$(REMOTE_DIR)/

# -----------------------------
# Update on device
# -----------------------------
update:
	ssh $(REMOTE) "cd $(REMOTE_DIR) && ./update.sh"

# -----------------------------
# Install on device
# -----------------------------
install:
	ssh $(REMOTE) "cd $(REMOTE_DIR) && ./install.sh"

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
