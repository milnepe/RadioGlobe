# Contributing to RadioGlobe

This document describes how code changes flow through the project. It reflects
the conventions already in use in the git history — read it alongside
[ARCHITECTURE.md](ARCHITECTURE.md) (how the code is structured) and
[README.md](README.md) (how to set up a device).

## Getting set up

Follow the "Developing with UV" section in [README.md](README.md) to clone the
repo, create a `uv` virtual environment on Python 3.11, and install
dependencies.

## Branching

- `master` is the stable branch. Only release commits and merges from
  `develop` land here.
- `develop` is the integration branch. Feature branches merge here first.
- Create feature branches off `develop` (or `master` for small fixes), named
  `feature/<short-name>` (e.g. `feature/shutdown`) or `wip/<short-name>` for
  work in progress:
  ```
  git checkout -b feature/my-change
  ```

## Making a change

1. Branch from `develop`.
2. Make your change, keeping it scoped to one concern per branch.
3. Add or update tests under `tests/` (unit) or `tests/integration/` (needs
   real hardware — see `tests/integration/README.md`).
4. Run the unit test suite:
   ```
   uv run pytest
   ```
   or, if you prefer, from the project root:
   ```
   pytest -q
   ```
5. Lint with `ruff` (config in `pyproject.toml`).
6. Build the package locally to validate the installable wheel and version
   generation:
   ```
   make build
   ```
7. Open a pull request against `develop` on GitHub. Commit messages for
   merges follow the pattern `<Branch description> (#<PR number>)`.

There is no CI pipeline configured yet — tests and linting must be run
locally before requesting review.

## Releasing

Releases are cut from `master` using the `Makefile`, which bumps the version
in `pyproject.toml`, commits it, and tags it:

```
make bump-patch   # 0.5.0 -> 0.5.1
make bump-minor   # 0.5.0 -> 0.6.0
make bump-major   # 0.5.0 -> 1.0.0
```

Each bump target creates a `Release vX.Y.Z` commit and a matching `vX.Y.Z`
git tag, but does not push — push explicitly once you're ready:

```
git push && git push --tags
```

`make release` chains a patch bump with deploy and install to the configured
device (see `REMOTE` in the `Makefile`) — use this only when releasing to
your own hardware target.

The `VERSION` file is generated (via `make build` or a version bump) from
`pyproject.toml` / `git describe`; it's git-ignored and never committed —
don't edit it by hand.

When you are ready to deploy a built wheel to a device, use `make deploy` for
normal installs or `make force-deploy` to reinstall the exact wheel into an
existing `/opt/radioglobe/venv` on the device.

## Reporting issues

Open an issue on GitHub if you hit a problem you can't resolve yourself.
