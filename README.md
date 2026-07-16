# Reconvene

Resume your Claude Code sessions from a browser tab. Reads
[ccrider](https://github.com/neilberkman/ccrider)'s session database, ranks your
projects by recent activity, and lets you pick up where you left off.

## Requires

- [ccrider](https://github.com/neilberkman/ccrider): `brew install neilberkman/tap/ccrider`
- The `claude` CLI (Claude Code), logged in
- macOS (the web GUI resumes by opening a new Terminal window via AppleScript)
- [fzf](https://github.com/junegunn/fzf) — only for the terminal picker: `brew install fzf`

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
reconvene              # asks: [1] Web view or [2] TUI, then syncs ccrider and opens it
reconvene --no-sync    # skip the ccrider sync step
reconvene -b           # TUI: also list automated-runs (bot) projects
```

Running `reconvene` in a terminal prompts you to choose the **Web view** (opens your browser to
the project journal) or the **TUI** (an fzf picker in the terminal that hands off to
`claude --resume` when you select a session). Non-interactive invocations run the web view.

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
