# Reconvene

Resume your Claude Code sessions from a browser tab. Reads
[ccrider](https://github.com/neilberkman/ccrider)'s session database, ranks your
projects by recent activity, and lets you pick up where you left off.

## Requires

- [ccrider](https://github.com/neilberkman/ccrider): `brew install neilberkman/tap/ccrider`
- The `claude` CLI (Claude Code), logged in
- macOS (resume opens a new Terminal window via AppleScript)

## Install

Install the `reconvene` command with pipx (recommended — isolated) or pip:

```bash
pipx install .
# or: pip install .
```

Or, to run straight from a checkout without installing, symlink the launcher onto your PATH:

```bash
ln -s "$PWD/bin/reconvene" ~/.local/bin/reconvene
```

## Usage

```bash
reconvene              # syncs ccrider, opens your browser to the project journal
reconvene --no-sync    # skip the ccrider sync step
```

First run has zero configuration — every project is classified automatically. Visit
Settings (linked from the main page) to override classification for a specific project,
or to choose how recap generation authenticates with Claude Code.

## Testing

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[test]"
PLAYWRIGHT_BROWSERS_PATH=$(pwd)/.playwright-browsers .venv/bin/playwright install chromium
PLAYWRIGHT_BROWSERS_PATH=$(pwd)/.playwright-browsers .venv/bin/pytest tests/
```

A project-local venv sidesteps PEP 668 "externally-managed-environment" errors on
Homebrew/distro Python installs, and `PLAYWRIGHT_BROWSERS_PATH` keeps the downloaded
browser binary inside the project directory instead of the shared home-directory cache.

E2E tests (`tests/e2e/`) drive a real browser against a real running server instance, with the
`claude` CLI and Terminal-launch automation always faked — no real subprocess or window is ever
spawned during tests.

See `THIRD_PARTY_LICENSES.md` for third-party software this project depends on.
