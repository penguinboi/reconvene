# Reconvene

Resume your Claude Code sessions from a browser tab. Reads
[ccrider](https://github.com/neilberkman/ccrider)'s session database, ranks your
projects by recent activity, and lets you pick up where you left off.

## Requires

- [ccrider](https://github.com/neilberkman/ccrider): `brew install neilberkman/tap/ccrider`
- The `claude` CLI (Claude Code), logged in
- macOS (resume opens a new Terminal window via AppleScript)

## Install

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

See `THIRD_PARTY_LICENSES.md` for third-party software this project depends on.
