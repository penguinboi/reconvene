# TUI Lazy Previews — Design

## What it is

Make the terminal picker generate each project's recap **lazily, on demand** — only for the
project you're currently highlighting — instead of generating recaps for every project up front.

## The problem

`run_tui` calls `ensure_recaps(shown, db, cache, config)` for **all** projects before launching
fzf. On a cold cache with `recap_auth_mode="claude_cli"`, that shells out to `claude -p` for every
uncached project (4 concurrent) with **no output** — so after the ccrider sync the terminal shows
nothing for minutes before fzf appears. It looks stuck/broken. (Found in a live smoke test; the
unit tests use `recap_auth_mode="none"`, which skips `claude`, so they never surfaced it.)

The web GUI does not have this problem: it renders the journal immediately and fetches each
project's recap lazily via `GET /api/recap/<name>`, one per card, only as needed. This design gives
the TUI the same lazy model.

Approved through the brainstorming process; the mechanism (a `sys.executable -m reconvene._preview`
per-item preview command, pure-lazy with a loading placeholder) was chosen explicitly.

## Mechanism: fzf's per-item preview command

fzf re-runs its `--preview` command for whichever row is highlighted and streams the command's
stdout into the preview pane. So instead of pre-writing every recap to temp files and doing
`cat <tmpdir>/{1}`, the preview command *is* a small program that generates-or-fetches one recap:

```
<sys.executable> -m reconvene._preview {1} <db> <cache> <config>
```

- `sys.executable` (not a bare `python`/`reconvene`) is used so the preview runs under the exact
  interpreter running the TUI — bulletproof across pipx/venv/system installs, no PATH assumptions.
- `{1}` is fzf's substitution for the highlighted row's hidden first column (the session id).
- `<db> <cache> <config>` are the same paths the TUI itself is using, baked into the command string
  by `run_tui` (shell-quoted).

## `reconvene/_preview.py` (new module)

`main(argv, *, recaps_fn=ensure_recaps) -> int` where `argv == [session_id, db_path, cache_path,
config_path]`. `recaps_fn` is injectable so tests never spawn `claude`. Behavior:

1. `config = load_config(config_path)`; `sessions = load_sessions(db_path)`; `build_journal`; find
   the project whose `latest.session_id == session_id`. If none, print `(project not found)` and
   return 0 (covers the bots separator row, whose id is empty, and deleted sessions).
2. Print the **stats header** immediately and flush (`render_header(project)` — name, session count,
   last-active, `~`-abbreviated path, separator rule) so the pane paints instantly.
3. **Cache-first body:** open `RecapCache(cache_path)`; compute the signature the same way
   `ensure_recaps` does (`signature(project.sessions[:RECENT_SESSIONS_FOR_RECAP])`) and
   `cache.get(project.name, sig)`.
   - **Hit** → print the cached full recap (instant on repeat views; `recaps_fn` is never called).
   - **Miss** → print `⏳ generating recap…` and flush, then call
     `recaps_fn([project], db_path, cache, config)` (which generates and caches), then print the
     result's full recap. fzf streams stdout, so the header + spinner line show first, then the
     recap appears when generation returns.
4. **Error handling:** the generation step is wrapped in `try/except`; any exception prints a single
   graceful line `⚠ recap unavailable: <reason>` — never a traceback. (`ensure_recaps` already
   surfaces LLM failures to stderr and returns a degraded fallback rather than raising, so in
   practice this catch is defense-in-depth for unexpected errors.)

A `if __name__ == "__main__": raise SystemExit(main(sys.argv[1:]))` guard makes `python -m
reconvene._preview` runnable.

## `reconvene/tui.py` changes

- **Remove** the up-front recap work from `run_tui`: no `RecapCache`, no `ensure_recaps`, no
  `tempfile.mkdtemp` + per-project preview-file loop. `run_tui` becomes: fzf check → `load_sessions`
  → `build_journal` → empty-check → `build_entries` → launch fzf with the per-item preview command →
  on selection, resume. Drop the now-unused `tempfile`, `pathlib.Path`, `RecapCache`,
  `ensure_recaps` imports; add `import os`/keep `sys`, `shlex` (for `sys.executable` and quoting).
- **Replace** `render_preview(project, full)` with `render_header(project) -> str` — just the stats
  block + separator rule (no recap body; the body is now printed separately by `_preview`).
  `_preview` imports `render_header` from `tui`.
- **Add** `_preview_command(db_path, cache_path, config_path) -> str` returning the fzf preview
  command string (`f"{shlex.quote(sys.executable)} -m reconvene._preview {{1}} ..."`), so the
  command construction is unit-testable without spawning fzf. `run_tui` uses it.
- **`_make_fzf_picker(preview_cmd)`** now takes the preview command string instead of a tmpdir; its
  fzf argv uses `--preview preview_cmd`.
- **`run_tui` signature** gains `config_path`: `run_tui(config, db_path, cache_path, config_path,
  show_bots=False, *, picker=None, resumer=exec_resume) -> int`. `cli.main` passes `args.config`.

## `reconvene/cli.py` change

One line: the tui dispatch becomes `(launch_tui or run_tui)(config, args.db, args.cache,
args.config, args.bots)` (adds `args.config`). The `test_main_tui_passes_bots_flag` fake's signature
updates to accept the extra positional.

## Testing (TDD, injected boundaries, no real fzf/claude)

- **`_preview.main`** (new `tests/test_preview.py`), against a seeded ccrider fixture DB:
  - unknown session id → prints `(project not found)`, returns 0.
  - cache **hit** (pre-`put` a recap under the correct signature) → prints the cached full recap and
    does **not** call an injected recorder `recaps_fn`.
  - cache **miss** with `recap_auth_mode="none"` (config written to a temp path) → prints the header,
    the `⏳ generating recap…` marker, then the derived first-user-message body (no `claude`).
  - injected `recaps_fn` that raises → prints `⚠ recap unavailable:` (graceful, no traceback).
- **`tui`**: `render_header` output (header fields, no body); `_preview_command` contains
  `sys.executable`, `-m reconvene._preview`, `{1}`, and the three paths; `run_tui` no longer calls
  recaps up front (inject a `recaps_fn`/picker and assert the picker is invoked with lines while no
  recap generation happened — simplest: assert `run_tui` returns without needing a cache and the
  injected picker receives the entry lines). Existing injected-picker/resumer `run_tui` tests are
  updated for the new `config_path` positional (a dummy path is fine — the injected picker ignores
  the preview command).
- **`cli`**: `test_main_tui_passes_bots_flag` updated for the new `run_tui` positional.

## Non-goals

- No up-front recap generation at all (pure lazy) — and no flag to restore the old behavior; the
  up-front generation was the bug.
- No change to the web GUI, resume/execvp, the startup chooser, or classification.
- No live-updating spinner animation — a single `⏳ generating recap…` line that the recap replaces
  is enough (fzf streaming handles the reveal).
- No caching changes — `RecapCache`/`ensure_recaps` are reused as-is; the per-item preview simply
  reads/writes the same cache one project at a time.
