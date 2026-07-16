# Terminal (TUI) Frontend — Design

## What it is

A second frontend for Reconvene: a terminal picker, alongside the existing web GUI, over the same
config-driven core (`journal`, `classify`, `recap`, `resume`, `config`, `db`). Running `reconvene`
presents a startup choice — **web view** or **TUI** — and launches the chosen frontend.

## Motivation

A private predecessor tool (`pickup`) already provides an fzf-based terminal picker over the same
ccrider data, but it bakes personal project names into `constants.py` and can't be published as-is.
Rather than genericize and maintain a second tool with its own divergent classification, this adds
the terminal frontend *into* reconvene, reusing reconvene's already-generic, PII-free core. One
codebase, one classification system, two frontends.

Approved through the brainstorming process; the key choices (fzf subprocess over stdlib curses;
execvp handoff over spawning a window; a startup chooser over a subcommand/flag) were made
explicitly.

## Startup chooser

`reconvene`, when stdin is an interactive TTY, prints a plain (stdlib, no fzf) prompt and reads a
choice:

```
Reconvene
  [1] Web view
  [2] TUI
>
```

- `1` launches the web GUI (today's behavior). `2` launches the terminal picker.
- The prompt is shown fresh every run — no remembered/default choice (YAGNI).
- If stdin is **not** a TTY (piped, scripted, CI), the chooser is skipped and the web GUI runs —
  preserving today's non-interactive behavior so nothing scripted breaks.
- Order per run: parse args → show chooser (if TTY) → `ccrider sync` unless `--no-sync` → launch
  the chosen frontend. The chooser comes before the sync so the user isn't made to wait to choose.
- The existing flags (`--no-sync`, `--db`, `--cache`, `--config`, `-V`) apply to whichever frontend
  is chosen. A new `-b`/`--bots` flag (TUI only) includes the automated-runs section, matching
  pickup.

## `reconvene/tui.py`

A new module holding the terminal picker, mirroring pickup's proven pattern but over reconvene's
core:

- `load_sessions(db_path)` → `build_journal(sessions, config)` for the ranked real projects (plus
  the bots list when `--bots` is set).
- `ensure_recaps(projects, db_path, RecapCache(cache_path), config)` up front to generate/cache the
  recaps, reusing the same cache the web GUI uses.
- For each project, write a preview file (a stats header — name, session count, last-active via
  `relative_time`, path via `abbreviate_home` — followed by the recap text) into a temp directory.
- Drive `fzf` as a subprocess: pipe `f"{session_id}\t{display_line}"` rows, with
  `--with-nth 2..` (hide the id column), `--preview "cat <tmpdir>/{1}"`,
  `--preview-window right:65%:wrap`, `--layout=reverse`, `--no-sort`, `--border=rounded`,
  `--info=inline` — the same flags pickup uses.
- The picker function is **injectable** (default builds the real fzf subprocess), so tests pass a
  fake picker and never spawn fzf.
- If `shutil.which("fzf")` is `None`, exit with a clear message:
  `reconvene: the terminal picker needs fzf — install it with: brew install fzf`.

## Resume: execvp handoff

On selection the TUI hands the current terminal to Claude Code (pickup's pattern), rather than
spawning a window (the web GUI's AppleScript pattern, which exists only because its server must keep
running):

- Add `exec_resume(session_id, cwd, updated_at, config=None, path_exists=os.path.isdir,
  execvp=os.execvp)` to `resume.py`, next to `open_terminal_and_resume`, so both resume strategies
  live together and share `resume_command`.
- Behavior: if `not path_exists(cwd)`, raise `FileNotFoundError` (same guard as the window path);
  otherwise `os.chdir(cwd)` then `execvp("claude", resume_command(session_id, updated_at,
  config.claude_extra_args if config else ""))`. This reuses the exact `resume_command` the web path
  builds, so the injected resume-context prompt is identical.
- `execvp` (and `path_exists`) are injectable so tests assert the call without replacing the test
  process.
- The TUI's selection handler is also injectable as a `resumer` (mirroring pickup's `cli.main`),
  defaulting to `exec_resume`, so unit tests inject a recording fake.

## Settings / classification

The TUI is **read-only** on config: it honors whatever the web Settings page manages (bot/hidden
classification, hidden-path substrings, recap auth mode, claude flags) by loading the same
`config.json`. No config editing in the terminal — classification changes stay in the web UI. This
keeps the TUI focused on browse-and-resume.

## Packaging / docs

- No new **Python** dependency. `fzf` is an external binary, like `ccrider` and `claude`; it is
  required only for the terminal picker (the web GUI needs nothing new).
- README "Requires" gains `fzf` (noted as needed only for the TUI, `brew install fzf`), and the
  usage section documents the startup chooser.
- `THIRD_PARTY_LICENSES.md` gains an `fzf` entry (MIT).
- The `reconvene` console-script entry point is unchanged — it just gains the chooser and the TUI
  branch. No second entry point.

## Testing

Unit tests only (a terminal frontend has no browser/e2e surface), mirroring pickup's `test_cli.py`
approach — real logic, injected boundaries, no real `fzf`/`claude`/process replacement:

- **Chooser**: injected stdin returns "1"/"2"/invalid/EOF → asserts the right frontend is selected
  (and that a non-TTY defaults to web).
- **tui line/preview rendering**: assert the ranked display lines and the preview file contents
  (stats header + recap) for a seeded ccrider fixture DB.
- **fzf command construction**: assert the argv/flags the picker builds (via the injected picker
  boundary), without spawning fzf.
- **Selection → resume**: an injected fake `resumer` records `(session_id, cwd, updated_at)`;
  assert the picked session maps to the right project path and updated_at. `--bots` visibility is
  asserted the way pickup asserts it.
- **`exec_resume`**: injected `path_exists`/`execvp` → asserts it chdirs and calls `execvp` with
  `resume_command`'s argv when the dir exists, and raises `FileNotFoundError` when it doesn't
  (never actually replacing the test process).

## Non-goals

- No curses/stdlib reimplementation of what fzf provides.
- No config editing in the TUI (browse + resume only; settings stay in the web UI).
- No remembered/default choice in the chooser (fresh prompt each run).
- No change to the web GUI, its API, or its resume mechanism — only the shared entry point gains the
  chooser, and `resume.py` gains the sibling `exec_resume`.
- Not publishing `pickup`; this supersedes the need to.
