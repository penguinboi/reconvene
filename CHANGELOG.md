# Changelog

Notable changes to Reconvene. Format loosely follows
[Keep a Changelog](https://keepachangelog.com/); versions use [SemVer](https://semver.org/).

## [Unreleased]

### Fixed
- **Resume was impossible for topic and loose groups in the web UI.** Their Resume button
  stayed disabled until a session row was clicked, but nothing marked the rows as choices
  and the row hover state was painted the modal's own background color, so it produced no
  visible change. Groups now preselect their latest session and keep the picker, the hover
  and selected states are visible, and a "Pick a session to resume:" label marks the rows.
  Root cause writeup: `docs/debugging/2026-08-10-resume-picker-root-cause.md`.
- Grammar in the prompt injected on resume: `verbose_age()` already ends in "ago", so the
  text read "inactive for 13 hours ago". Now "was last active 13 hours ago".

### Changed
- The web resume modal preselects a group's latest session, superseding the 0.2.0 behavior
  below for the web. The TUI still requires an explicit pick for a multi-session group.

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
