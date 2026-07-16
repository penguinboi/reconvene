# TUI Lazy Previews Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the TUI generate each project's recap lazily (per highlighted item, via an fzf `--preview` command) instead of blocking on `ensure_recaps` for all projects up front.

**Architecture:** `run_tui` stops generating recaps and launches fzf immediately; its `--preview` command is `<sys.executable> -m reconvene._preview {1} <db> <cache> <config>`, a new module that renders one project's header instantly and fetches-or-generates just that project's recap (cache-first, with a loading placeholder on a miss).

**Tech Stack:** Python 3.11+ standard library only. External binaries `fzf`/`claude` as today. pytest.

## Global Constraints

- Standard-library-only Python; no new dependency.
- No up-front recap generation at all — `run_tui` must not call `ensure_recaps`/`RecapCache`. Lazy only; no flag to restore the old behavior.
- The preview command uses `sys.executable` (not bare `python`/`reconvene`) so it runs under the same interpreter as the TUI.
- The preview module must never print a traceback: generation errors become a single `⚠ recap unavailable: <reason>` line; an unknown session id prints `(project not found)`.
- Every test injects its boundaries (a fake picker, a fake resumer, an injected `recaps_fn`, a temp `recap_auth_mode="none"` config) so no real `fzf`/`claude` runs.
- `run_tui`'s signature gains `config_path` as the 4th positional argument: `run_tui(config, db_path, cache_path, config_path, show_bots=False, *, picker=None, resumer=exec_resume)`.
- Run tests with `.venv/bin/python -m pytest <path> -v`.

**Existing interfaces to reuse (as-is):**
- `reconvene/recap.py`: `signature(sessions) -> str`; `RECENT_SESSIONS_FOR_RECAP` (also importable from `reconvene.constants`); `ensure_recaps(projects, db_path, cache, config, runner=None) -> dict[name -> (oneline, full)]`; `RecapCache(path)` with `.get(project, sig) -> (oneline, full) | None`, `.put(project, sig, oneline, full)`, `.close()`; `claude_runner` (module-level, monkeypatchable).
- `reconvene/journal.py`: `build_journal(sessions, config) -> (real, bots)`; `relative_time`; `abbreviate_home`. `Project` has `.name/.count/.last_active/.latest`; `.latest` is a `Session` with `.session_id/.project_path/.updated_at`.
- `reconvene/db.py`: `load_sessions(db_path)`. `reconvene/config.py`: `load_config(path)`, `save_config(config, path)`.

---

### Task 1: Make `run_tui` lazy (tui.py + cli.py + test edits)

**Files:**
- Modify: `reconvene/tui.py`
- Modify: `reconvene/cli.py`
- Modify: `tests/test_tui.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: `build_journal`, `relative_time`, `abbreviate_home`, `exec_resume`, `load_sessions` (existing).
- Produces: `render_header(project) -> str`; `_preview_command(db_path, cache_path, config_path) -> str`; `_make_fzf_picker(preview_cmd)`; `run_tui(config, db_path, cache_path, config_path, show_bots=False, *, picker=None, resumer=exec_resume) -> int`. Task 2's `_preview` imports `render_header`; the preview command names `reconvene._preview` (created in Task 2 — Task 1 only references it as a string).

- [ ] **Step 1: Edit the tests**

In `tests/test_tui.py`:

(1a) Replace the `render_preview` test with a `render_header` test:

```python
def test_render_header_has_stats_no_body():
    p = _p("myproject", "real", "s1", "/Users/x/Code/myproject", "2026-07-08 10:00:00", count=2)
    out = tui.render_header(p)
    assert "myproject" in out
    assert "2 sessions" in out
    assert "/Users/x/Code/myproject" in out or "~/Code/myproject" in out  # abbreviated path
```

(1b) Add `config_path` to every existing `run_tui(...)` call by inserting a config-path argument right after the cache-path argument. Do this with a single replace-all in `tests/test_tui.py`: replace every occurrence of

```
str(tmp_path / "r.db")
```

with

```
str(tmp_path / "r.db"), str(tmp_path / "c.json")
```

(This appends `config_path` as the 4th positional to all seven `run_tui` calls, including the single-line one in `test_run_tui_missing_fzf_returns_1`.)

(1c) Append two new tests to `tests/test_tui.py`:

```python
def test_preview_command_references_the_preview_module_and_paths():
    import sys as _sys
    cmd = tui._preview_command("/db/sessions.db", "/cache/recaps.db", "/cfg/config.json")
    assert _sys.executable in cmd
    assert "-m reconvene._preview" in cmd
    assert "{1}" in cmd  # fzf substitutes the hidden session-id column
    assert "/db/sessions.db" in cmd and "/cache/recaps.db" in cmd and "/cfg/config.json" in cmd


def test_run_tui_does_not_generate_recaps_up_front(tmp_path, ccrider_db, monkeypatch):
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "hi", sequence=1)
    # Config() defaults to recap_auth_mode="claude_cli"; if run_tui still generated recaps up front
    # it would call claude_runner. Record calls and assert it never happens.
    called = []
    monkeypatch.setattr("reconvene.recap.claude_runner",
                        lambda *a, **k: called.append(1) or "ONELINE: x\nDETAIL: x")
    seen = {}
    tui.run_tui(
        Config(), str(ccrider_db), str(tmp_path / "r.db"), str(tmp_path / "c.json"),
        picker=lambda lines: seen.setdefault("lines", lines) and None,
        resumer=lambda *a: None,
    )
    assert seen["lines"]   # picker was reached with entry lines
    assert called == []    # no recap generation up front
```

In `tests/test_cli.py`, update the `test_main_tui_passes_bots_flag` fake to accept the new `config_path` positional. Change:

```python
        launch_tui=lambda config, db, cache, show_bots: captured.setdefault("show_bots", show_bots) or 0,
```

to:

```python
        launch_tui=lambda config, db, cache, config_path, show_bots: captured.setdefault("show_bots", show_bots) or 0,
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_tui.py tests/test_cli.py -q`
Expected: FAIL — `render_header`/`_preview_command` don't exist yet, and `run_tui` doesn't accept the extra positional. (The `render_preview` test is gone.)

- [ ] **Step 3: Rewrite `reconvene/tui.py`**

Replace the entire contents of `reconvene/tui.py` with:

```python
# ABOUTME: Terminal frontend — an fzf picker over the ranked journal that hands off to claude --resume.
# ABOUTME: Recaps load lazily per highlighted item via an fzf --preview command (reconvene._preview).
import shlex
import shutil
import subprocess
import sys

from .db import load_sessions
from .journal import abbreviate_home, build_journal, relative_time
from .resume import exec_resume

SEPARATOR_SID = ""


def render_line(project) -> str:
    return f"{project.name} · {relative_time(project.last_active)} · {project.count} sessions"


def render_header(project) -> str:
    latest = project.latest
    return "\n".join([
        project.name,
        f"{project.count} sessions · last {relative_time(project.last_active)}",
        f"path  {abbreviate_home(latest.project_path)}",
        "─" * 46,
    ])


def build_entries(real, bots, show_bots):
    entries = [(render_line(p), p.latest.session_id) for p in real]
    if show_bots and bots:
        entries.append(("──────── automated ────────", SEPARATOR_SID))
        entries.extend((render_line(p), p.latest.session_id) for p in bots)
    return entries


def _preview_command(db_path, cache_path, config_path) -> str:
    # fzf substitutes {1} with the highlighted row's hidden session-id column, then runs this per
    # item and streams its stdout into the preview pane. sys.executable keeps us on the same
    # interpreter as the running TUI (robust under pipx/venv/system installs).
    return (
        f"{shlex.quote(sys.executable)} -m reconvene._preview {{1}} "
        f"{shlex.quote(db_path)} {shlex.quote(cache_path)} {shlex.quote(config_path)}"
    )


def _make_fzf_picker(preview_cmd):
    def picker(lines):
        proc = subprocess.run(
            ["fzf", "--no-sort", "--layout=reverse", "--border=rounded", "--info=inline",
             "--delimiter", "\t", "--with-nth", "2..",
             "--preview", preview_cmd,
             "--preview-window", "right:65%:wrap"],
            input="\n".join(lines), capture_output=True, text=True,
        )
        return proc.stdout.strip() or None
    return picker


def run_tui(config, db_path, cache_path, config_path, show_bots=False, *, picker=None, resumer=exec_resume) -> int:
    if picker is None and shutil.which("fzf") is None:
        print("reconvene: the terminal picker needs fzf — install it with: brew install fzf",
              file=sys.stderr)
        return 1

    sessions = load_sessions(db_path)
    real, bots = build_journal(sessions, config)
    shown = real + (bots if show_bots else [])
    if not shown:
        if bots:  # bots exist but are hidden without --bots
            print("No projects to show. Use -b to include automated-runs projects.", file=sys.stderr)
        else:
            print("No projects found.", file=sys.stderr)
        return 1

    entries = build_entries(real, bots, show_bots)
    sid_to_project = {p.latest.session_id: p for p in shown}
    lines = [f"{sid}\t{display}" for display, sid in entries]
    active_picker = picker or _make_fzf_picker(_preview_command(db_path, cache_path, config_path))
    chosen = active_picker(lines)

    if not chosen:
        return 0
    sid = chosen.split("\t", 1)[0]
    project = sid_to_project.get(sid)
    if project is None:
        return 0  # separator or unrecognized line
    resumer(sid, project.latest.project_path, project.latest.updated_at, config)
    return 0
```

- [ ] **Step 4: Update the `cli.py` dispatch**

In `reconvene/cli.py`, change the tui dispatch line:

```python
    if mode == "tui":
        return (launch_tui or run_tui)(config, args.db, args.cache, args.bots)
```

to:

```python
    if mode == "tui":
        return (launch_tui or run_tui)(config, args.db, args.cache, args.config, args.bots)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_tui.py tests/test_cli.py -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add reconvene/tui.py reconvene/cli.py tests/test_tui.py tests/test_cli.py
git commit -m "feat: TUI launches instantly, previews load lazily per item"
```

---

### Task 2: `reconvene/_preview.py` — the per-item preview target

**Files:**
- Create: `reconvene/_preview.py`
- Test: `tests/test_preview.py`

**Interfaces:**
- Consumes: `render_header` (Task 1), `load_config`, `load_sessions`, `build_journal`, `RecapCache`, `ensure_recaps`, `signature`, `RECENT_SESSIONS_FOR_RECAP`.
- Produces: `main(argv, *, recaps_fn=ensure_recaps) -> int` invoked as `python -m reconvene._preview <sid> <db> <cache> <config>`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_preview.py`:

```python
# ABOUTME: Tests for the fzf preview target — cache-first recap rendering, graceful errors.
# ABOUTME: Uses a temp 'none'-mode config so ensure_recaps derives from the first message, no claude.
import io
from contextlib import redirect_stdout

from reconvene.config import Config, save_config
from reconvene.constants import RECENT_SESSIONS_FOR_RECAP
from reconvene.db import load_sessions
from reconvene.journal import build_journal
from reconvene.recap import RecapCache, signature
from reconvene import _preview
from tests.conftest import add_session, add_message


def _none_config(tmp_path):
    p = tmp_path / "config.json"
    save_config(Config(recap_auth_mode="none"), p)
    return str(p)


def test_preview_unknown_session_prints_not_found(tmp_path, ccrider_db):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = _preview.main(["no-such-sid", str(ccrider_db), str(tmp_path / "r.db"), _none_config(tmp_path)])
    assert rc == 0
    assert "(project not found)" in buf.getvalue()


def test_preview_cache_hit_prints_cached_recap_without_generating(tmp_path, ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "hi", sequence=1)
    config = Config(recap_auth_mode="none")
    project = build_journal(load_sessions(str(ccrider_db)), config)[0][0]
    sig = signature(project.sessions[:RECENT_SESSIONS_FOR_RECAP])
    cache = RecapCache(str(tmp_path / "r.db"))
    cache.put(project.name, sig, "one", "the cached full recap")
    cache.close()

    called = []
    buf = io.StringIO()
    with redirect_stdout(buf):
        _preview.main(["s1", str(ccrider_db), str(tmp_path / "r.db"), _none_config(tmp_path)],
                      recaps_fn=lambda *a: called.append(1) or {})
    out = buf.getvalue()
    assert "the cached full recap" in out
    assert "⏳" not in out    # no loading marker on a hit
    assert called == []       # generation never invoked on a hit


def test_preview_cache_miss_shows_loading_then_derived_recap(tmp_path, ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "wire up the thresholds", sequence=1)
    buf = io.StringIO()
    with redirect_stdout(buf):
        _preview.main(["s1", str(ccrider_db), str(tmp_path / "r.db"), _none_config(tmp_path)])  # real ensure_recaps, none -> derive
    out = buf.getvalue()
    assert "myproject" in out                # header
    assert "⏳ generating recap…" in out      # loading marker on a miss
    assert "wire up the thresholds" in out   # derived recap = first user message


def test_preview_generation_failure_is_graceful(tmp_path, ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "hi", sequence=1)
    def boom(*a):
        raise RuntimeError("claude exploded")
    buf = io.StringIO()
    with redirect_stdout(buf):
        _preview.main(["s1", str(ccrider_db), str(tmp_path / "r.db"), _none_config(tmp_path)], recaps_fn=boom)
    out = buf.getvalue()
    assert "⚠ recap unavailable" in out
    assert "claude exploded" in out
    assert "Traceback" not in out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_preview.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'reconvene._preview'`.

- [ ] **Step 3: Create `reconvene/_preview.py`**

```python
# ABOUTME: fzf --preview target — prints one project's stats header + recap on demand.
# ABOUTME: Cache-first; generates (via claude) only on a miss, so the TUI never blocks up front.
import sys

from .config import load_config
from .constants import RECENT_SESSIONS_FOR_RECAP
from .db import load_sessions
from .journal import build_journal
from .recap import RecapCache, ensure_recaps, signature
from .tui import render_header


def _find_project(config, db_path, session_id):
    real, bots = build_journal(load_sessions(db_path), config)
    return next((p for p in real + bots if p.latest.session_id == session_id), None)


def _recap_body(project, db_path, cache_path, config, recaps_fn):
    cache = RecapCache(cache_path)
    try:
        sig = signature(project.sessions[:RECENT_SESSIONS_FOR_RECAP])
        hit = cache.get(project.name, sig)
        if hit is not None:
            return hit[1]
        print("⏳ generating recap…", flush=True)
        result = recaps_fn([project], db_path, cache, config)
        return result.get(project.name, ("", "(no recap)"))[1]
    finally:
        cache.close()


def main(argv, *, recaps_fn=ensure_recaps) -> int:
    session_id, db_path, cache_path, config_path = argv[0], argv[1], argv[2], argv[3]
    try:
        config = load_config(config_path)
        project = _find_project(config, db_path, session_id)
    except Exception as e:
        # Bad db/config path etc. — never dump a traceback into the preview pane.
        print(f"⚠ recap unavailable: {e}")
        return 0
    if project is None:
        print("(project not found)")
        return 0
    print(render_header(project), flush=True)
    print()  # blank line between header and body
    try:
        body = _recap_body(project, db_path, cache_path, config, recaps_fn)
    except Exception as e:
        body = f"⚠ recap unavailable: {e}"
    print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_preview.py -q`
Expected: all PASS.

- [ ] **Step 5: Run the whole suite and confirm `python -m reconvene._preview` is runnable**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all PASS.

Run: `.venv/bin/python -m reconvene._preview no-such-sid /nonexistent.db /tmp/none.db /nonexistent.json`
Expected: prints a single `⚠ recap unavailable: …` line (the missing DB path fails `load_sessions`, caught by `main`'s outer try) and exits 0 — no Python traceback.

- [ ] **Step 6: Commit**

```bash
git add reconvene/_preview.py tests/test_preview.py
git commit -m "feat: add reconvene._preview — lazy per-item recap for the TUI"
```
