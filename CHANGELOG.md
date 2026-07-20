# Changelog

Notable changes to Reconvene. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versions use [SemVer](https://semver.org/).

## [0.2.0] — 2026-07-20

### Added
- **Full-text session search** — the web top-bar box, the TUI's `ctrl-f`, and
  `reconvene -s "query"` — over ccrider's existing FTS5 index, with the matching
  text highlighted in each result.
- **Per-session resume**: resume any session, not just a project's latest. The web
  resume modal lists a project's sessions to pick from; in the TUI, `ctrl-s` drills
  into a project's session list.
- **Topic clustering** of sessions launched from a root directory (e.g. bare `~/Code`):
  `reconvene --organize` (or a web "Organize into topics" button) has Claude sort them
  into named topic groups. Assignments are cached and never reshuffled.
- **Per-session recaps** in the search / drill-in preview (cache-first), with a
  "building summary" note shown only on the first, generating open.
- **Key-hint headers** on the TUI pickers (`enter` / `ctrl-s` / `ctrl-f` / `esc`).
- **Linux support** for the web resume — it launches a terminal emulator
  (`$TERMINAL` or a detected gnome-terminal / konsole / alacritty / kitty / xterm).
  The TUI's in-place resume already worked cross-platform.

### Changed
- Pressing Enter on a loose or topic group now opens the session picker instead of
  resuming an arbitrary "latest" session; a real project still resumes its latest.

## [0.1.0]

### Added
- Initial release: a ranked per-project journal over ccrider's session history,
  AI-generated recaps, a local web GUI and an fzf TUI, and resume via `claude --resume`.
