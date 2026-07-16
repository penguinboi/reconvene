# TUI Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a terminal (fzf) frontend to Reconvene, chosen at startup alongside the web GUI, reusing the existing config-driven core.

**Architecture:** A new `reconvene/tui.py` drives `fzf` as a subprocess over the ranked journal (same `load_sessions`→`build_journal`→`ensure_recaps` flow as the web GUI) and resumes via a new `exec_resume` in `resume.py` that hands the terminal to `claude --resume` with `os.execvp`. `reconvene/cli.py`'s `main()` gains a startup chooser (Web view / TUI) that dispatches to either frontend; both share the existing flags.

**Tech Stack:** Python 3.11+ standard library only. External binaries: `fzf` (TUI only), `ccrider`, `claude` (as today). pytest.

## Global Constraints

- Standard-library-only Python; no new Python dependency. `fzf` is an external binary required **only** for the TUI (the web GUI needs nothing new).
- Every test must inject its boundaries — a fake picker, a fake resumer, injected stdin, and injected `execvp`/`chdir`/`path_exists` — so no real `fzf`, `claude`, terminal, or process-replacement ever happens during tests. Use `.venv/bin/python -m pytest <path> -v`.
- Recaps in tests avoid `claude` by using `Config(recap_auth_mode="none")`, which makes `ensure_recaps` use the first-user-message fallback (no subprocess).
- The web GUI, its HTTP API, and its AppleScript resume path are unchanged. `main()`'s new parameters are keyword-only with behavior-preserving defaults.
- The chooser shows fresh every run when stdin is a TTY; a non-TTY invocation skips it and runs the web GUI (today's behavior).

**Interfaces that already exist (consume as-is):**
- `reconvene/resume.py`: `resume_command(session_id, updated_at, extra_args="", now=None) -> list[str]` (returns `["claude", "--resume", session_id, ...extra_args..., prompt]`).
- `reconvene/journal.py`: `build_journal(sessions, config) -> (real, bots)`; `relative_time(last_active, now=None) -> str`; `abbreviate_home(path, home=None) -> str`. `Project` has `.name`, `.count`, `.last_active`, `.latest` (a `Session` with `.session_id`, `.project_path`, `.updated_at`).
- `reconvene/recap.py`: `ensure_recaps(projects, db_path, cache, config, runner=None, concurrency=...) -> dict[name -> (oneline, full)]`; `RecapCache(path)` with `.close()`.
- `reconvene/db.py`: `load_sessions(db_path) -> list[Session]`.
- `reconvene/cli.py`: `find_free_port(...)`, `main(argv=None)`.

---

### Task 1: `exec_resume` — foreground execvp handoff

**Files:**
- Modify: `reconvene/resume.py`
- Test: `tests/test_resume.py`

**Interfaces:**
- Consumes: `resume_command` (existing).
- Produces: `exec_resume(session_id: str, cwd: str, updated_at: str, config=None, path_exists=os.path.isdir, chdir=os.chdir, execvp=os.execvp) -> None`. Task 2 calls it as the default resumer.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_resume.py` (it already imports `pytest` and defines `UPDATED_AT = "2026-07-15 10:00:00"`; add `exec_resume` to the existing `from reconvene.resume import (...)` block):

```python
def test_exec_resume_chdirs_then_execs_claude(tmp_path):
    d = tmp_path / "proj"
    d.mkdir()
    calls = {}
    exec_resume(
        "s1", str(d), UPDATED_AT,
        chdir=lambda p: calls.__setitem__("chdir", p),
        execvp=lambda file, args: calls.__setitem__("exec", (file, args)),
    )
    assert calls["chdir"] == str(d)
    file, args = calls["exec"]
    assert file == "claude"
    assert args[:3] == ["claude", "--resume", "s1"]
    assert "Resuming session from" in args[-1]  # the injected resume-context prompt


def test_exec_resume_includes_configured_extra_args(tmp_path):
    from reconvene.config import Config
    d = tmp_path / "proj"
    d.mkdir()
    captured = {}
    exec_resume(
        "s1", str(d), UPDATED_AT, config=Config(claude_extra_args="--dangerously-skip-permissions"),
        chdir=lambda p: None,
        execvp=lambda file, args: captured.__setitem__("args", args),
    )
    assert "--dangerously-skip-permissions" in captured["args"]


def test_exec_resume_raises_when_directory_missing(tmp_path):
    missing = str(tmp_path / "gone")  # never created; default path_exists=os.path.isdir
    called = []
    with pytest.raises(FileNotFoundError, match="gone"):
        exec_resume("s1", missing, UPDATED_AT,
                    chdir=lambda p: called.append("chdir"),
                    execvp=lambda file, args: called.append("exec"))
    assert called == []  # neither chdir nor execvp ran
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_resume.py -k exec_resume -v`
Expected: FAIL — `ImportError: cannot import name 'exec_resume'`.

- [ ] **Step 3: Implement `exec_resume`**

In `reconvene/resume.py`, add after `open_terminal_and_resume`:

```python
def exec_resume(session_id: str, cwd: str, updated_at: str, config=None,
                path_exists=os.path.isdir, chdir=os.chdir, execvp=os.execvp) -> None:
    # Foreground handoff for the TUI: replace this process with `claude --resume` in the
    # project's directory. Unlike open_terminal_and_resume (which must spawn a window because the
    # web server keeps running), the TUI is a foreground process, so execvp gives the terminal
    # straight to Claude. Reuses resume_command so the injected resume-context prompt is identical.
    if not path_exists(cwd):
        raise FileNotFoundError(f"project directory no longer exists: {cwd}")
    extra_args = config.claude_extra_args if config else ""
    chdir(cwd)
    execvp("claude", resume_command(session_id, updated_at, extra_args))
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_resume.py -v`
Expected: all PASS (the three new tests plus the existing resume tests).

- [ ] **Step 5: Commit**

```bash
git add reconvene/resume.py tests/test_resume.py
git commit -m "feat: add exec_resume for foreground TUI resume via execvp"
```

---

### Task 2: `reconvene/tui.py` — the fzf picker

**Files:**
- Create: `reconvene/tui.py`
- Test: `tests/test_tui.py`

**Interfaces:**
- Consumes: `load_sessions`, `build_journal`, `relative_time`, `abbreviate_home`, `ensure_recaps`, `RecapCache`, `exec_resume`.
- Produces: `render_line(project) -> str`; `render_preview(project, full) -> str`; `build_entries(real, bots, show_bots) -> list[(display, session_id)]`; `run_tui(config, db_path, cache_path, show_bots=False, *, picker=None, resumer=exec_resume) -> int`. Task 3 calls `run_tui`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_tui.py`:

```python
# ABOUTME: Tests for the terminal frontend — rendering, entry ordering, and run_tui dispatch.
# ABOUTME: Injects a fake picker + fake resumer so no real fzf/claude ever runs.
from reconvene.config import Config
from reconvene.db import Session
from reconvene.journal import Project
from reconvene import tui
from tests.conftest import add_session, add_message


def _p(name, cat, sid, path, updated, count=1):
    return Project(name, cat, [Session(sid, path, updated, updated, 5, None, None) for _ in range(count)])


def test_render_line_format():
    p = _p("myproject", "real", "s1", "/Users/x/Code/myproject", "2026-07-08 10:00:00", count=2)
    line = tui.render_line(p)
    assert "myproject" in line and "2 sessions" in line and "·" in line


def test_render_preview_has_stats_and_recap():
    p = _p("myproject", "real", "s1", "/Users/x/Code/myproject", "2026-07-08 10:00:00")
    out = tui.render_preview(p, "did the sensor work")
    assert "myproject" in out
    assert "/Users/x/Code/myproject" in out or "~/Code/myproject" in out  # abbreviated path
    assert "did the sensor work" in out


def test_build_entries_orders_real_then_bots():
    real = [_p("realproj", "real", "r1", "/p/realproj", "2026-07-08 00:00:00")]
    bots = [_p("botproj", "bot", "b1", "/p/botproj", "2026-07-09 00:00:00")]
    entries = tui.build_entries(real, bots, show_bots=True)
    displays = [d for d, _ in entries]
    assert "realproj" in displays[0]
    assert any("automated" in d.lower() for d in displays)  # separator present
    assert entries[-1][1] == "b1"


def test_run_tui_resumes_selected(tmp_path, ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "wire up thresholds", sequence=1)
    resumed = []
    rc = tui.run_tui(
        Config(recap_auth_mode="none"), str(ccrider_db), str(tmp_path / "r.db"),
        picker=lambda lines: lines[0],  # pick the first entry ("s1\t...")
        resumer=lambda sid, cwd, updated_at, config: resumed.append((sid, cwd, updated_at)),
    )
    assert rc == 0
    assert resumed == [("s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00")]


def test_run_tui_no_pick_returns_0(tmp_path, ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "hi", sequence=1)
    resumed = []
    rc = tui.run_tui(
        Config(recap_auth_mode="none"), str(ccrider_db), str(tmp_path / "r.db"),
        picker=lambda lines: None,  # user pressed ESC
        resumer=lambda *a: resumed.append(a),
    )
    assert rc == 0
    assert resumed == []


def test_run_tui_separator_pick_does_not_resume(tmp_path, ccrider_db):
    add_session(ccrider_db, "b1", "/Users/x/Code/scoutbot", "2026-07-09 00:00:00", message_count=2)
    add_message(ccrider_db, "b1", "user", "score idea", sequence=1)
    add_session(ccrider_db, "r1", "/Users/x/Code/realproj", "2026-07-08 00:00:00", message_count=40)
    add_message(ccrider_db, "r1", "user", "real work", sequence=1)
    resumed = []
    rc = tui.run_tui(
        Config(recap_auth_mode="none", bot_names={"scoutbot"}), str(ccrider_db), str(tmp_path / "r.db"),
        show_bots=True,
        picker=lambda lines: next(l for l in lines if "automated" in l.lower()),  # the separator row
        resumer=lambda *a: resumed.append(a),
    )
    assert rc == 0
    assert resumed == []


def test_run_tui_empty_returns_1(tmp_path, ccrider_db):
    resumed = []
    rc = tui.run_tui(
        Config(recap_auth_mode="none"), str(ccrider_db), str(tmp_path / "r.db"),
        picker=lambda lines: lines[0] if lines else None,
        resumer=lambda *a: resumed.append(a),
    )
    assert rc == 1
    assert resumed == []


def test_run_tui_bots_hidden_without_flag(tmp_path, ccrider_db):
    add_session(ccrider_db, "b1", "/Users/x/Code/scoutbot", "2026-07-09 00:00:00", message_count=2)
    add_message(ccrider_db, "b1", "user", "score idea", sequence=1)
    seen = {}
    tui.run_tui(
        Config(recap_auth_mode="none", bot_names={"scoutbot"}), str(ccrider_db), str(tmp_path / "r.db"),
        show_bots=False,
        picker=lambda lines: seen.setdefault("lines", lines) and None,
        resumer=lambda *a: None,
    )
    assert all("scoutbot" not in l for l in seen["lines"])  # bot section not shown


def test_run_tui_missing_fzf_returns_1(tmp_path, ccrider_db, monkeypatch):
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "hi", sequence=1)
    monkeypatch.setattr("reconvene.tui.shutil.which", lambda name: None)
    rc = tui.run_tui(Config(recap_auth_mode="none"), str(ccrider_db), str(tmp_path / "r.db"))  # no picker -> real path
    assert rc == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_tui.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'reconvene.tui'`.

- [ ] **Step 3: Implement `reconvene/tui.py`**

Create `reconvene/tui.py`:

```python
# ABOUTME: Terminal frontend — an fzf picker over the ranked journal that hands off to claude --resume.
# ABOUTME: Mirrors the web GUI's data flow (journal + recaps) but resumes via execvp in the foreground.
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .db import load_sessions
from .journal import abbreviate_home, build_journal, relative_time
from .recap import RecapCache, ensure_recaps
from .resume import exec_resume

SEPARATOR_SID = ""


def render_line(project) -> str:
    return f"{project.name} · {relative_time(project.last_active)} · {project.count} sessions"


def render_preview(project, full) -> str:
    latest = project.latest
    stats = "\n".join([
        project.name,
        f"{project.count} sessions · last {relative_time(project.last_active)}",
        f"path  {abbreviate_home(latest.project_path)}",
    ])
    return f"{stats}\n{'─' * 46}\n\n{full}"


def build_entries(real, bots, show_bots):
    entries = [(render_line(p), p.latest.session_id) for p in real]
    if show_bots and bots:
        entries.append(("──────── automated ────────", SEPARATOR_SID))
        entries.extend((render_line(p), p.latest.session_id) for p in bots)
    return entries


def _make_fzf_picker(tmpdir):
    def picker(lines):
        proc = subprocess.run(
            ["fzf", "--no-sort", "--layout=reverse", "--border=rounded", "--info=inline",
             "--delimiter", "\t", "--with-nth", "2..",
             "--preview", "cat " + shlex.quote(tmpdir) + "/{1} 2>/dev/null",
             "--preview-window", "right:65%:wrap"],
            input="\n".join(lines), capture_output=True, text=True,
        )
        out = proc.stdout.strip()
        return out or None
    return picker


def run_tui(config, db_path, cache_path, show_bots=False, *, picker=None, resumer=exec_resume) -> int:
    if picker is None and shutil.which("fzf") is None:
        print("reconvene: the terminal picker needs fzf — install it with: brew install fzf",
              file=sys.stderr)
        return 1

    sessions = load_sessions(db_path)
    real, bots = build_journal(sessions, config)
    shown = real + (bots if show_bots else [])
    if not shown:
        print("No projects found.", file=sys.stderr)
        return 1

    cache = RecapCache(cache_path)
    try:
        recaps = ensure_recaps(shown, db_path, cache, config)
    finally:
        cache.close()

    tmpdir = tempfile.mkdtemp(prefix="reconvene-")
    try:
        for p in shown:
            full = recaps.get(p.name, ("", "(no recap)"))[1]
            Path(tmpdir, p.latest.session_id).write_text(render_preview(p, full))
        entries = build_entries(real, bots, show_bots)
        sid_to_project = {p.latest.session_id: p for p in shown}
        lines = [f"{sid}\t{display}" for display, sid in entries]
        active_picker = picker or _make_fzf_picker(tmpdir)
        chosen = active_picker(lines)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    if not chosen:
        return 0
    sid = chosen.split("\t", 1)[0]
    project = sid_to_project.get(sid)
    if project is None:
        return 0  # separator or unrecognized line
    resumer(sid, project.latest.project_path, project.latest.updated_at, config)
    return 0
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_tui.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add reconvene/tui.py tests/test_tui.py
git commit -m "feat: add reconvene.tui — fzf terminal picker over the journal"
```

---

### Task 3: Startup chooser in `cli.py`

**Files:**
- Modify: `reconvene/cli.py`
- Modify: `tests/test_cli.py` (already exists — append to it; do not overwrite)

**Interfaces:**
- Consumes: `run_tui` (Task 2), the existing web serve path.
- Produces: `_choose_frontend(input_fn=input) -> str | None` (returns `"web"`, `"tui"`, or `None` on EOF); a refactored `main(argv=None, *, input_fn=input, stdin_isatty=None, launch_web=None, launch_tui=None) -> int`; and `_serve_web(config, db, cache, config_path) -> int` (the existing web launch, extracted).

- [ ] **Step 1: Update the two existing `main()` tests, then add the chooser/dispatch tests**

`tests/test_cli.py` already exists (find_free_port tests + two `main()` error-path tests). It must
be **modified, not replaced**. First, make the two existing `main()` tests robust to the new
chooser by passing `stdin_isatty=False` (non-interactive → web, matching their intent — they
predate the chooser). Change:

```python
    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    rc = cli.main([])
```

to:

```python
    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    rc = cli.main([], stdin_isatty=False)
```

and change:

```python
    monkeypatch.setattr(cli, "find_free_port", lambda: (_ for _ in ()).throw(RuntimeError("no free port found in range 4242-4251")))
    rc = cli.main(["--no-sync"])
```

to:

```python
    monkeypatch.setattr(cli, "find_free_port", lambda: (_ for _ in ()).throw(RuntimeError("no free port found in range 4242-4251")))
    rc = cli.main(["--no-sync"], stdin_isatty=False)
```

Then **append** these tests to the end of `tests/test_cli.py` (the file already has
`from reconvene import cli`):

```python
def test_choose_frontend_web():
    assert cli._choose_frontend(input_fn=lambda prompt: "1") == "web"


def test_choose_frontend_tui():
    assert cli._choose_frontend(input_fn=lambda prompt: "2") == "tui"


def test_choose_frontend_reprompts_on_bad_input():
    answers = iter(["x", "", "2"])
    assert cli._choose_frontend(input_fn=lambda prompt: next(answers)) == "tui"


def test_choose_frontend_none_on_eof():
    def eof(prompt):
        raise EOFError
    assert cli._choose_frontend(input_fn=eof) is None


def test_main_non_tty_defaults_to_web(tmp_path):
    calls = []
    rc = cli.main(
        ["--no-sync", "--db", str(tmp_path / "x.db"), "--config", str(tmp_path / "c.json")],
        stdin_isatty=False,
        launch_web=lambda *a, **k: calls.append("web") or 0,
        launch_tui=lambda *a, **k: calls.append("tui") or 0,
    )
    assert rc == 0
    assert calls == ["web"]


def test_main_chooser_picks_tui(tmp_path):
    calls = []
    rc = cli.main(
        ["--no-sync", "--db", str(tmp_path / "x.db"), "--config", str(tmp_path / "c.json")],
        stdin_isatty=True, input_fn=lambda prompt: "2",
        launch_web=lambda *a, **k: calls.append("web") or 0,
        launch_tui=lambda *a, **k: calls.append("tui") or 0,
    )
    assert rc == 0
    assert calls == ["tui"]


def test_main_chooser_picks_web(tmp_path):
    calls = []
    rc = cli.main(
        ["--no-sync", "--db", str(tmp_path / "x.db"), "--config", str(tmp_path / "c.json")],
        stdin_isatty=True, input_fn=lambda prompt: "1",
        launch_web=lambda *a, **k: calls.append("web") or 0,
        launch_tui=lambda *a, **k: calls.append("tui") or 0,
    )
    assert calls == ["web"]


def test_main_chooser_eof_returns_0_without_launching(tmp_path):
    calls = []
    def eof(prompt):
        raise EOFError
    rc = cli.main(
        ["--no-sync", "--db", str(tmp_path / "x.db"), "--config", str(tmp_path / "c.json")],
        stdin_isatty=True, input_fn=eof,
        launch_web=lambda *a, **k: calls.append("web") or 0,
        launch_tui=lambda *a, **k: calls.append("tui") or 0,
    )
    assert rc == 0
    assert calls == []


def test_main_tui_passes_bots_flag(tmp_path):
    captured = {}
    cli.main(
        ["-b", "--no-sync", "--db", str(tmp_path / "x.db"), "--config", str(tmp_path / "c.json")],
        stdin_isatty=True, input_fn=lambda prompt: "2",
        launch_web=lambda *a, **k: 0,
        launch_tui=lambda config, db, cache, show_bots: captured.setdefault("show_bots", show_bots) or 0,
    )
    assert captured["show_bots"] is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_cli.py -v`
Expected: FAIL — `AttributeError: module 'reconvene.cli' has no attribute '_choose_frontend'` (and `main()` rejects the new keyword args).

- [ ] **Step 3: Refactor `cli.py`**

Replace the whole body of `reconvene/cli.py` below the imports. First update the imports block at the top:

```python
# ABOUTME: CLI entry point — a startup chooser dispatches to the web GUI or the terminal picker.
# ABOUTME: Both frontends share ccrider sync and the same flags (--db/--cache/--config/--no-sync).
import argparse
import socket
import subprocess
import sys
import threading
import webbrowser

from .config import load_config
from .constants import CCRIDER_DB, CONFIG_PATH, RECAP_CACHE_DB, VERSION
from .resume import open_terminal_and_resume
from .tui import run_tui
from .web.server import serve
```

Keep `find_free_port` exactly as it is. Then add `_choose_frontend` and `_serve_web`, and replace `main`:

```python
def _choose_frontend(input_fn=input):
    print("Reconvene")
    print("  [1] Web view")
    print("  [2] TUI")
    while True:
        try:
            choice = input_fn("> ").strip()
        except EOFError:
            return None
        if choice == "1":
            return "web"
        if choice == "2":
            return "tui"
        print("Please enter 1 or 2.", file=sys.stderr)


def _serve_web(config, db, cache, config_path) -> int:
    try:
        port = find_free_port()
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    resumer = lambda session_id, cwd, updated_at: open_terminal_and_resume(session_id, cwd, updated_at, config)
    server = serve(config, db, cache, config_path, resumer, port=port)
    url = f"http://127.0.0.1:{port}"
    print(f"Reconvene running at {url}")
    threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def main(argv=None, *, input_fn=input, stdin_isatty=None,
         launch_web=None, launch_tui=None) -> int:
    ap = argparse.ArgumentParser(prog="reconvene", description="Resume a Claude Code project by its journal.")
    ap.add_argument("--no-sync", action="store_true", help="skip `ccrider sync` first")
    ap.add_argument("-b", "--bots", action="store_true", help="TUI: include the automated-runs section")
    ap.add_argument("--db", default=str(CCRIDER_DB), help="ccrider sessions DB path")
    ap.add_argument("--cache", default=str(RECAP_CACHE_DB), help="recap cache path")
    ap.add_argument("--config", default=str(CONFIG_PATH), help="config file path")
    ap.add_argument("-V", "--version", action="version", version=f"reconvene {VERSION}")
    args = ap.parse_args(argv)

    interactive = sys.stdin.isatty() if stdin_isatty is None else stdin_isatty
    mode = _choose_frontend(input_fn) if interactive else "web"
    if mode is None:
        return 0  # user cancelled the chooser

    if not args.no_sync and args.db == str(CCRIDER_DB):
        try:
            result = subprocess.run(["ccrider", "sync"])
        except FileNotFoundError:
            print(
                "error: `ccrider` isn't installed or isn't on PATH.\n"
                "Install it with: brew install neilberkman/tap/ccrider",
                file=sys.stderr,
            )
            return 1
        if result.returncode != 0:
            print(f"warning: `ccrider sync` exited {result.returncode}; showing possibly-stale data", file=sys.stderr)

    config = load_config(args.config)
    if mode == "tui":
        return (launch_tui or run_tui)(config, args.db, args.cache, args.bots)
    return (launch_web or _serve_web)(config, args.db, args.cache, args.config)
```

Note: `run_tui`'s signature is `run_tui(config, db_path, cache_path, show_bots=False, ...)`, so the positional `args.bots` binds to `show_bots`. The `test_main_tui_passes_bots_flag` test's fake uses the keyword name `show_bots` — call it positionally here; the test's lambda `lambda config, db, cache, show_bots` accepts it positionally.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_cli.py -v`
Expected: all PASS.

- [ ] **Step 5: Run the whole suite to confirm nothing regressed**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all PASS (existing web/e2e tests unaffected — `_serve_web` is the same launch logic they never invoked directly, and `main`'s new params default to the old behavior).

- [ ] **Step 6: Commit**

```bash
git add reconvene/cli.py tests/test_cli.py
git commit -m "feat: startup chooser dispatching to the web GUI or the TUI"
```

---

### Task 4: Documentation — fzf requirement and the chooser

**Files:**
- Modify: `README.md`
- Modify: `THIRD_PARTY_LICENSES.md`

**Interfaces:** none (docs only).

- [ ] **Step 1: Update the README Requires and Usage**

In `README.md`, change the Requires list to add fzf (TUI-only). Replace:

```markdown
- [ccrider](https://github.com/neilberkman/ccrider): `brew install neilberkman/tap/ccrider`
- The `claude` CLI (Claude Code), logged in
- macOS (resume opens a new Terminal window via AppleScript)
```

with:

```markdown
- [ccrider](https://github.com/neilberkman/ccrider): `brew install neilberkman/tap/ccrider`
- The `claude` CLI (Claude Code), logged in
- macOS (the web GUI resumes by opening a new Terminal window via AppleScript)
- [fzf](https://github.com/junegunn/fzf) — only for the terminal picker: `brew install fzf`
```

Then replace the Usage section:

```markdown
## Usage

```bash
reconvene              # syncs ccrider, opens your browser to the project journal
reconvene --no-sync    # skip the ccrider sync step
```
```

with:

```markdown
## Usage

```bash
reconvene              # asks: [1] Web view or [2] TUI, then syncs ccrider and opens it
reconvene --no-sync    # skip the ccrider sync step
reconvene -b           # TUI: also list automated-runs (bot) projects
```

Running `reconvene` in a terminal prompts you to choose the **Web view** (opens your browser to
the project journal) or the **TUI** (an fzf picker in the terminal that hands off to
`claude --resume` when you select a session). Non-interactive invocations run the web view.
```

- [ ] **Step 2: Add fzf to THIRD_PARTY_LICENSES.md**

In `THIRD_PARTY_LICENSES.md`, add after the `## ccrider` block:

```markdown
## fzf

- Repository: https://github.com/junegunn/fzf
- License: MIT
- Copyright (c) Junegunn Choi
- Used only by the terminal picker (`reconvene` → TUI); invoked as an external command.
```

- [ ] **Step 3: Commit**

```bash
git add README.md THIRD_PARTY_LICENSES.md
git commit -m "docs: document the fzf-based TUI and the startup chooser"
```
