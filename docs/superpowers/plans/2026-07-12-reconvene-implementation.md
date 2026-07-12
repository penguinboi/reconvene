# Reconvene Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Reconvene, a standalone, public, PII-free local web app that reads ccrider's session database, ranks/classifies projects, and lets the user resume a Claude Code session from a browser tab.

**Architecture:** A single Python process (stdlib only, no third-party pip dependencies) starts a `ThreadingHTTPServer` bound to `127.0.0.1`, serving a small JSON API plus static HTML/CSS/vanilla-JS pages. Core logic (session loading, classification, ranking, recap generation) is ported from the private `pickup` tool, generalized to read a user-editable `Config` instead of hardcoded personal constants.

**Tech Stack:** Python 3.11+, stdlib only (`http.server`, `sqlite3`, `subprocess`, `threading`, `webbrowser`, `json`, `dataclasses`), `pytest` for tests. External runtime dependencies (not pip packages): `ccrider` CLI (MIT, must be installed separately) and the `claude` CLI (Claude Code).

## Global Constraints

- Stdlib only — no third-party pip dependencies, matching pickup's existing philosophy (from spec's Architecture section).
- Claude Code only for v1 — no multi-agent support, even though ccrider tracks 5 agent CLIs (spec's Non-goals).
- macOS only for v1 — the resume action opens a new Terminal window via a macOS-specific mechanism (spec's Non-goals).
- No PII ever committed to git — `config.json` (project names, overrides) lives only in `~/.config/reconvene/`, never in the repo (spec's Distribution & PII section).
- `BOT_PROMOTE_MESSAGE_COUNT = 30` and `NOISE_MESSAGE_FLOOR = 2` are fixed built-in heuristic defaults, not user-configurable in v1 (spec's Components section).
- MIT license for the repo, with a `THIRD_PARTY_LICENSES.md` crediting ccrider (MIT, Neil Berkman) (spec's Distribution & PII section).

---

## Task 1: Scaffold the repo

**Files:**
- Create: `pyproject.toml`
- Create: `LICENSE`
- Create: `.gitignore`
- Create: `THIRD_PARTY_LICENSES.md`
- Create: `reconvene/__init__.py`
- Create: `bin/reconvene`
- Test: none (scaffolding only; verified by import in Task 2)

Note: `README.md` is NOT created here — its content is defined in Task 13 (Step 5), which is where it belongs since it documents the finished CLI's usage.

**Interfaces:**
- Produces: an installable `reconvene` package with entry point `bin/reconvene`, matching pickup's install pattern (symlink `bin/reconvene` onto PATH, or `pipx install -e .`).

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "reconvene"
version = "0.1.0"
requires-python = ">=3.11"

[project.scripts]
reconvene = "reconvene.cli:main"

[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create `LICENSE`** (MIT, standard text)

```
MIT License

Copyright (c) 2026 Skyler Lister Aley

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 3: Create `THIRD_PARTY_LICENSES.md`**

```markdown
# Third-Party Licenses

Reconvene depends on the following software at runtime. It does not vendor or
redistribute their source; they must be installed separately.

## ccrider

- Repository: https://github.com/neilberkman/ccrider
- License: MIT
- Copyright (c) Neil Berkman

## Claude Code (`claude` CLI)

- Anthropic's Claude Code CLI. Requires a separate Anthropic account.
```

- [ ] **Step 4: Create `.gitignore`**

```
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
```

- [ ] **Step 5: Create `reconvene/__init__.py`** (empty)

```python
```

- [ ] **Step 6: Create `bin/reconvene`**

```python
#!/usr/bin/env python3
# ABOUTME: Executable entry so `reconvene` can be symlinked onto PATH.
# ABOUTME: Resolves the repo root from its own real path (following symlinks), then runs the CLI.
import os
import sys

repo = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
sys.path.insert(0, repo)

from reconvene.cli import main

raise SystemExit(main())
```

- [ ] **Step 7: Make `bin/reconvene` executable**

Run: `chmod +x bin/reconvene`

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml LICENSE .gitignore THIRD_PARTY_LICENSES.md reconvene/__init__.py bin/reconvene
git commit -m "chore: scaffold reconvene package"
```

(Note: `reconvene/cli.py`, imported by `bin/reconvene`, doesn't exist yet — that's fine, this task only scaffolds; `bin/reconvene` isn't run until Task 13.)

---

## Task 2: `constants.py`

**Files:**
- Create: `reconvene/constants.py`
- Test: `tests/test_constants.py`

**Interfaces:**
- Produces: `HOME`, `CCRIDER_DB`, `RECAP_CACHE_DB`, `CONFIG_PATH`, `DROP_SUBSTRINGS`, `WORKTREE_MARKERS`, `OVERRIDE_MAP`, `BOT_PROMOTE_MESSAGE_COUNT`, `NOISE_MESSAGE_FLOOR`, `RECENT_SESSIONS_FOR_RECAP`, `RECAP_CONCURRENCY`, `MODEL`, `VERSION`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_constants.py
# ABOUTME: Tests for constants derived at import time rather than hardcoded.
# ABOUTME: Verifies VERSION is read from pyproject.toml, not duplicated by hand.
import tomllib
from pathlib import Path

from reconvene.constants import VERSION, BOT_PROMOTE_MESSAGE_COUNT, NOISE_MESSAGE_FLOOR


def test_version_matches_pyproject():
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    with pyproject.open("rb") as f:
        declared = tomllib.load(f)["project"]["version"]
    assert VERSION == declared


def test_heuristic_thresholds_are_the_validated_defaults():
    assert BOT_PROMOTE_MESSAGE_COUNT == 30
    assert NOISE_MESSAGE_FLOOR == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_constants.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'reconvene.constants'`

- [ ] **Step 3: Write minimal implementation**

```python
# reconvene/constants.py
# ABOUTME: Paths and tunable constants for reconvene.
# ABOUTME: No personal project names live here — those go in the user's config.json.
import tomllib
from pathlib import Path


def _read_version() -> str:
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    with pyproject.open("rb") as f:
        return tomllib.load(f)["project"]["version"]


VERSION = _read_version()

HOME = Path.home()
CCRIDER_DB = HOME / ".config" / "ccrider" / "sessions.db"
RECAP_CACHE_DB = HOME / ".config" / "reconvene" / "recaps.db"
CONFIG_PATH = HOME / ".config" / "reconvene" / "config.json"

DROP_SUBSTRINGS = ("/private/", "/scratchpad")
WORKTREE_MARKERS = ("/.claude-worktrees/", "/.worktrees/", "--claude-worktrees")
OVERRIDE_MAP: dict[str, str] = {}

BOT_PROMOTE_MESSAGE_COUNT = 30
NOISE_MESSAGE_FLOOR = 2

RECENT_SESSIONS_FOR_RECAP = 3
RECAP_CONCURRENCY = 4
MODEL = "sonnet"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_constants.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add reconvene/constants.py tests/test_constants.py
git commit -m "feat: add constants module with no personal data"
```

---

## Task 3: `config.py`

**Files:**
- Create: `reconvene/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `CONFIG_PATH` from `reconvene.constants`.
- Produces: `Config` dataclass with fields `code_root: str | None`, `bot_names: set[str]`, `hidden_names: set[str]`, `recap_auth_mode: str` (one of `"claude_cli"`, `"api_key"`, `"none"`), `api_key: str | None`. Functions `load_config(path=CONFIG_PATH) -> Config` and `save_config(config: Config, path=CONFIG_PATH) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
# ABOUTME: Tests for Config load/save round-trip and defaults.
# ABOUTME: Verifies a missing config file yields sensible zero-config defaults.
import json

from reconvene.config import Config, load_config, save_config


def test_load_config_missing_file_returns_defaults(tmp_path):
    config = load_config(tmp_path / "does-not-exist.json")
    assert config.code_root is None
    assert config.bot_names == set()
    assert config.hidden_names == set()
    assert config.recap_auth_mode == "claude_cli"
    assert config.api_key is None


def test_save_then_load_round_trips(tmp_path):
    path = tmp_path / "config.json"
    config = Config(
        code_root="/Users/x/Code",
        bot_names={"scoutbot"},
        hidden_names={"scratch-repo"},
        recap_auth_mode="api_key",
        api_key="sk-test",
    )
    save_config(config, path)
    loaded = load_config(path)
    assert loaded == config


def test_save_creates_parent_directory(tmp_path):
    path = tmp_path / "nested" / "dir" / "config.json"
    save_config(Config(), path)
    assert path.exists()
    assert json.loads(path.read_text())["recap_auth_mode"] == "claude_cli"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'reconvene.config'`

- [ ] **Step 3: Write minimal implementation**

```python
# reconvene/config.py
# ABOUTME: User-editable configuration — the generalization layer that replaces
# ABOUTME: pickup's hardcoded constants.py. Persisted to ~/.config/reconvene/config.json.
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .constants import CONFIG_PATH


@dataclass
class Config:
    code_root: str | None = None
    bot_names: set[str] = field(default_factory=set)
    hidden_names: set[str] = field(default_factory=set)
    recap_auth_mode: str = "claude_cli"
    api_key: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["bot_names"] = sorted(self.bot_names)
        d["hidden_names"] = sorted(self.hidden_names)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Config":
        return cls(
            code_root=d.get("code_root"),
            bot_names=set(d.get("bot_names", [])),
            hidden_names=set(d.get("hidden_names", [])),
            recap_auth_mode=d.get("recap_auth_mode", "claude_cli"),
            api_key=d.get("api_key"),
        )


def load_config(path=CONFIG_PATH) -> Config:
    path = Path(path)
    if not path.exists():
        return Config()
    with path.open() as f:
        return Config.from_dict(json.load(f))


def save_config(config: Config, path=CONFIG_PATH) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(config.to_dict(), f, indent=2)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add reconvene/config.py tests/test_config.py
git commit -m "feat: add user-editable Config with load/save round-trip"
```

---

## Task 4: `db.py` and shared test fixtures

**Files:**
- Create: `reconvene/db.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Produces: `Session` frozen dataclass (`session_id, project_path, updated_at, created_at, message_count, llm_summary, summary`), `load_sessions(db_path) -> list[Session]`, `session_messages(db_path, session_id, limit=40) -> list[tuple[str, str]]`, `probe_schema(conn)`.
- Produces (test infra): pytest fixture `ccrider_db(tmp_path)`, helpers `add_session(...)`/`add_message(...)` — used by every later task's tests.

- [ ] **Step 1: Write the failing test**

```python
# tests/__init__.py
```

```python
# tests/conftest.py
# ABOUTME: pytest fixture providing a temporary ccrider SQLite DB with the schema subset.
# ABOUTME: Helpers add_session and add_message for test data setup.
import sqlite3
import pytest


@pytest.fixture
def ccrider_db(tmp_path):
    db = tmp_path / "sessions.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE sessions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          session_id TEXT, project_path TEXT, cwd TEXT, summary TEXT, llm_summary TEXT,
          created_at DATETIME, updated_at DATETIME, message_count INTEGER,
          git_branch TEXT, provider TEXT
        );
        CREATE TABLE messages (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          session_id INTEGER, uuid TEXT, parent_uuid TEXT, type TEXT, sender TEXT,
          content TEXT, text_content TEXT, timestamp DATETIME,
          is_sidechain INTEGER, sequence INTEGER
        );
        """
    )
    conn.commit()
    conn.close()
    return db


def add_session(db, session_id, project_path, updated_at,
                created_at="2026-01-01 00:00:00", message_count=10,
                llm_summary=None, summary=None):
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO sessions(session_id,project_path,cwd,summary,llm_summary,created_at,updated_at,message_count)"
        " VALUES(?,?,?,?,?,?,?,?)",
        (session_id, project_path, project_path, summary, llm_summary, created_at, updated_at, message_count),
    )
    conn.commit()
    conn.close()


def add_message(db, session_id, role, body, sequence, is_sidechain=0):
    sender = "human" if role == "user" else role
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO messages(session_id,type,sender,content,text_content,is_sidechain,sequence)"
        " VALUES((SELECT id FROM sessions WHERE session_id=?),?,?,?,?,?,?)",
        (session_id, role, sender, body, body, is_sidechain, sequence),
    )
    conn.commit()
    conn.close()
```

```python
# tests/test_db.py
# ABOUTME: Tests for read-only ccrider DB access.
# ABOUTME: Verifies row loading, schema validation, and read-only connection mode.
import sqlite3

import pytest

from reconvene.db import load_sessions, probe_schema, session_messages
from tests.conftest import add_session, add_message


def test_load_sessions_reads_rows(ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/regrade3", "2026-07-08 10:00:00", message_count=42)
    sessions = load_sessions(str(ccrider_db))
    assert len(sessions) == 1
    assert sessions[0].session_id == "s1"
    assert sessions[0].message_count == 42


def test_probe_schema_raises_on_missing_column(tmp_path):
    db = tmp_path / "broken.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE sessions (id INTEGER PRIMARY KEY)")
    conn.commit()
    with pytest.raises(RuntimeError, match="missing columns"):
        probe_schema(conn)
    conn.close()


def test_connection_is_read_only(ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/regrade3", "2026-07-08 10:00:00")
    load_sessions(str(ccrider_db))  # must not raise or lock the file
    # a second independent connection must still be able to write (proves the
    # read-only connection didn't hold a lock)
    conn = sqlite3.connect(ccrider_db)
    conn.execute("UPDATE sessions SET message_count = 99 WHERE session_id = 's1'")
    conn.commit()
    conn.close()


def test_session_messages_orders_and_skips_sidechain(ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/regrade3", "2026-07-08 10:00:00")
    add_message(ccrider_db, "s1", "assistant", "hi", sequence=1)
    add_message(ccrider_db, "s1", "user", "do the sensor task", sequence=2)
    add_message(ccrider_db, "s1", "user", "side note", sequence=3, is_sidechain=1)
    msgs = session_messages(str(ccrider_db), "s1")
    assert msgs == [("assistant", "hi"), ("user", "do the sensor task")]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_db.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'reconvene.db'`

- [ ] **Step 3: Write minimal implementation**

```python
# reconvene/db.py
# ABOUTME: Read-only access to ccrider's SQLite session DB (sessions + messages tables).
# ABOUTME: Fails loudly if ccrider's schema drifts; never writes to the DB.
import sqlite3
from dataclasses import dataclass

REQUIRED_SESSION_COLS = {
    "session_id", "project_path", "summary", "llm_summary",
    "created_at", "updated_at", "message_count",
}


@dataclass(frozen=True)
class Session:
    session_id: str
    project_path: str
    updated_at: str
    created_at: str
    message_count: int
    llm_summary: str | None
    summary: str | None


def _connect(db_path):
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def probe_schema(conn):
    conn.row_factory = sqlite3.Row
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(sessions)")}
    missing = REQUIRED_SESSION_COLS - cols
    if missing:
        raise RuntimeError(
            f"ccrider sessions table missing columns: {sorted(missing)} — ccrider schema changed?"
        )


def load_sessions(db_path) -> list[Session]:
    conn = _connect(db_path)
    try:
        probe_schema(conn)
        rows = conn.execute(
            "SELECT session_id, project_path, summary, llm_summary, created_at, updated_at, message_count FROM sessions"
        ).fetchall()
    finally:
        conn.close()
    return [
        Session(
            r["session_id"], r["project_path"], r["updated_at"], r["created_at"],
            r["message_count"] or 0, r["llm_summary"], r["summary"],
        )
        for r in rows
    ]


def session_messages(db_path, session_id, limit=40) -> list[tuple[str, str]]:
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT type, COALESCE(NULLIF(text_content,''), content) AS body "
            "FROM messages WHERE session_id = (SELECT id FROM sessions WHERE session_id=?) "
            "AND (is_sidechain IS NULL OR is_sidechain=0) "
            "ORDER BY sequence LIMIT ?",
            (session_id, limit),
        ).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        body = (r["body"] or "").strip()
        if body:
            out.append(((r["type"] or ""), body))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_db.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add reconvene/db.py tests/__init__.py tests/conftest.py tests/test_db.py
git commit -m "feat: add read-only ccrider DB access and shared test fixtures"
```

---

## Task 5: `classify.py`

**Files:**
- Create: `reconvene/classify.py`
- Test: `tests/test_classify.py`

**Interfaces:**
- Consumes: `Config` from `reconvene.config` (fields `code_root`, `bot_names`, `hidden_names`); `DROP_SUBSTRINGS`, `WORKTREE_MARKERS`, `OVERRIDE_MAP`, `BOT_PROMOTE_MESSAGE_COUNT`, `NOISE_MESSAGE_FLOOR` from `reconvene.constants`.
- Produces: `canonical_name(project_path: str) -> str`, `classify_category(project_path: str, config: Config, message_count: int | None = None) -> str` (returns `"drop"`, `"bot"`, or `"real"`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_classify.py
# ABOUTME: Tests for session-path classification (drop/bot/real) and canonical project naming.
# ABOUTME: Verifies worktree/case folding, config-driven overrides, and heuristic promote/drop rules.
from reconvene.classify import canonical_name, classify_category
from reconvene.config import Config


def test_canonical_folds_worktree_and_case():
    assert canonical_name("/Users/x/Code/curtail/regrade3") == "regrade3"
    assert canonical_name("/Users/x/Code/regrade3") == "regrade3"
    assert canonical_name("/Users/x/Code/curtail/regrade3/.claude-worktrees/h2") == "regrade3"
    assert canonical_name("/Users/x/Code/penguinboisoftware/PenguinClock") == "penguinclock"


def test_classify_drops_scratch_paths():
    config = Config()
    assert classify_category("/private/tmp/claude-503/x/scratchpad", config) == "drop"


def test_classify_real_by_default_with_no_code_root():
    # zero-config: no code_root set, project is real unless config says otherwise
    config = Config()
    assert classify_category("/Users/x/Code/regrade3", config, message_count=10) == "real"


def test_classify_respects_code_root_when_set():
    config = Config(code_root="/Users/x/Code")
    assert classify_category("/Users/x/Downloads/thing", config, message_count=10) == "drop"
    assert classify_category("/Users/x/Code/regrade3", config, message_count=10) == "real"


def test_classify_bot_names_override():
    config = Config(bot_names={"scoutbot"})
    assert classify_category("/Users/x/Code/scoutbot", config, message_count=2) == "bot"


def test_classify_hidden_names_override():
    config = Config(hidden_names={"scratch-repo"})
    assert classify_category("/Users/x/Code/scratch-repo", config, message_count=10) == "drop"


def test_classify_promotes_long_bot_sessions_to_real():
    config = Config(bot_names={"scoutbot"})
    assert classify_category("/Users/x/Code/scoutbot", config, message_count=2) == "bot"
    assert classify_category("/Users/x/Code/scoutbot", config, message_count=31) == "real"


def test_classify_drops_trivial_real_sessions():
    config = Config()
    assert classify_category("/Users/x/Code/anything", config, message_count=2) == "drop"
    assert classify_category("/Users/x/Code/anything", config, message_count=3) == "real"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_classify.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'reconvene.classify'`

- [ ] **Step 3: Write minimal implementation**

```python
# reconvene/classify.py
# ABOUTME: Classifies a session's project_path (drop/bot/real) and derives a canonical project name.
# ABOUTME: Folds git-worktree paths and case; bot/hidden lists and code_root come from the user's Config.
from .constants import (
    DROP_SUBSTRINGS, WORKTREE_MARKERS, OVERRIDE_MAP,
    BOT_PROMOTE_MESSAGE_COUNT, NOISE_MESSAGE_FLOOR,
)


def canonical_name(project_path: str) -> str:
    p = project_path.rstrip("/")
    for marker in WORKTREE_MARKERS:
        idx = p.find(marker)
        if idx != -1:
            p = p[:idx]
            break
    name = p.rsplit("/", 1)[-1].lower()
    return OVERRIDE_MAP.get(name, name)


def classify_category(project_path: str, config, message_count: int | None = None) -> str:
    for sub in DROP_SUBSTRINGS:
        if sub in project_path:
            return "drop"
    name = canonical_name(project_path)
    if name in config.hidden_names:
        return "drop"
    if name in config.bot_names:
        if message_count is not None and message_count > BOT_PROMOTE_MESSAGE_COUNT:
            return "real"
        return "bot"
    if config.code_root and not (
        project_path == config.code_root or project_path.startswith(config.code_root + "/")
    ):
        return "drop"
    if message_count is not None and message_count <= NOISE_MESSAGE_FLOOR:
        return "drop"
    return "real"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_classify.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add reconvene/classify.py tests/test_classify.py
git commit -m "feat: add config-driven classification, no hardcoded project names"
```

---

## Task 6: `journal.py`

**Files:**
- Create: `reconvene/journal.py`
- Test: `tests/test_journal.py`

**Interfaces:**
- Consumes: `Session` from `reconvene.db`; `classify_category`, `canonical_name` from `reconvene.classify`; `Config` from `reconvene.config`.
- Produces: `Project` dataclass (`name: str, category: str, sessions: list[Session]`, properties `latest`, `count`, `last_active`), `build_journal(sessions, config) -> tuple[list[Project], list[Project]]` (returns `(real, bots)`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_journal.py
# ABOUTME: Tests for journal model — grouping, splitting, and ranking sessions.
# ABOUTME: Verifies project aggregation, real vs bot classification, and recency ranking.
from reconvene.config import Config
from reconvene.db import Session
from reconvene.journal import build_journal


def S(sid, path, updated, message_count=10):
    return Session(sid, path, updated, updated, message_count, None, None)


def test_build_journal_groups_ranks_and_splits():
    config = Config(bot_names={"penguinbot"})
    sessions = [
        S("a", "/Users/x/Code/curtail/regrade3", "2026-07-01 00:00:00"),
        S("b", "/Users/x/Code/regrade3",        "2026-07-08 00:00:00"),  # same project, newer
        S("c", "/Users/x/Code/penguinboisoftware/we-drew-this", "2026-07-05 00:00:00"),
        S("d", "/Users/x/Code/penguinboisoftware/penguinbot",   "2026-07-09 00:00:00"),  # bot
        S("e", "/private/tmp/x/scratchpad",    "2026-07-10 00:00:00"),  # dropped
    ]
    real, bots = build_journal(sessions, config)
    assert [p.name for p in real] == ["regrade3", "we-drew-this"]  # regrade3 newest (b) first
    assert real[0].count == 2 and real[0].latest.session_id == "b"
    assert [p.name for p in bots] == ["penguinbot"]


def test_build_journal_promotes_long_bot_sessions_and_drops_noise():
    config = Config(bot_names={"penguinbot"})
    sessions = [
        S("f", "/Users/x/Code/penguinboisoftware/penguinbot", "2026-07-09 00:00:00", message_count=3397),
        S("g", "/Users/x/Code/penguinboisoftware/penguinbot/afterdark", "2026-07-09 01:00:00", message_count=2),
        S("h", "/Users/x/Code/penguinboisoftware/keepsule", "2026-07-09 02:00:00", message_count=2),
        S("i", "/Users/x/Code/penguinboisoftware/keepsule", "2026-07-09 03:00:00", message_count=40),
    ]
    real, bots = build_journal(sessions, config)
    real_names = {p.name for p in real}
    assert "penguinbot" in real_names  # promoted: long session in a bot-named project
    assert "keepsule" in real_names
    keepsule = next(p for p in real if p.name == "keepsule")
    assert keepsule.count == 1 and keepsule.latest.session_id == "i"  # noisy session dropped
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_journal.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'reconvene.journal'`

- [ ] **Step 3: Write minimal implementation**

```python
# reconvene/journal.py
# ABOUTME: Rolls classified sessions into ranked per-project journal entries.
# ABOUTME: Real projects and bot projects are returned as two separately-sorted lists.
from dataclasses import dataclass

from .classify import classify_category, canonical_name
from .db import Session


@dataclass
class Project:
    name: str
    category: str
    sessions: list[Session]

    @property
    def latest(self) -> Session:
        return self.sessions[0]

    @property
    def count(self) -> int:
        return len(self.sessions)

    @property
    def last_active(self) -> str:
        return self.latest.updated_at


def build_journal(sessions, config):
    groups: dict[tuple[str, str], list[Session]] = {}
    for s in sessions:
        cat = classify_category(s.project_path, config, s.message_count)
        if cat == "drop":
            continue
        groups.setdefault((cat, canonical_name(s.project_path)), []).append(s)
    projects = []
    for (cat, name), sess in groups.items():
        sess.sort(key=lambda s: s.updated_at, reverse=True)
        projects.append(Project(name=name, category=cat, sessions=sess))
    real = sorted((p for p in projects if p.category == "real"),
                  key=lambda p: p.last_active, reverse=True)
    bots = sorted((p for p in projects if p.category == "bot"),
                  key=lambda p: p.last_active, reverse=True)
    return real, bots
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_journal.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add reconvene/journal.py tests/test_journal.py
git commit -m "feat: add config-driven project journal grouping and ranking"
```

---

## Task 7: `recap.py`

**Files:**
- Create: `reconvene/recap.py`
- Test: `tests/test_recap.py`

**Interfaces:**
- Consumes: `MODEL`, `RECENT_SESSIONS_FOR_RECAP`, `RECAP_CONCURRENCY` from `reconvene.constants`; `session_messages` from `reconvene.db`; `Config` from `reconvene.config`.
- Produces: `RecapCache` class (`get`, `put`, `close`), `build_prompt(project, db_path, ...)`, `parse_recap(output) -> tuple[str, str]`, `first_user_message(db_path, session_id, limit=90) -> str`, `derive_recap(project, db_path) -> tuple[str, str]`, `claude_runner(prompt, config, model=MODEL, timeout=120) -> str`, `generate_recap(project, db_path, runner) -> tuple[str, str]`, `ensure_recaps(projects, db_path, cache, config, runner=None, concurrency=RECAP_CONCURRENCY) -> dict[str, tuple[str, str]]`, `signature(sessions) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_recap.py
# ABOUTME: Tests for claude_runner-backed recap generation and ensure_recaps caching/pooling.
# ABOUTME: Uses injected fake runners so no real `claude` process is ever spawned.
import tempfile

from reconvene.config import Config
from reconvene.db import Session
from reconvene.journal import Project
from reconvene.recap import claude_runner, ensure_recaps, generate_recap, RecapCache


def _project(db, name):
    from tests.conftest import add_session, add_message
    add_session(db, "s1", f"/Users/x/Code/{name}", "2026-07-08 10:00:00", message_count=5)
    add_message(db, "s1", "user", "do the thing", sequence=1)
    return Project(name, "real", [Session("s1", f"/Users/x/Code/{name}", "2026-07-08 10:00:00", "x", 5, None, None)])


def test_generate_recap_uses_injected_runner(ccrider_db):
    p = _project(ccrider_db, "regrade3")
    fake = lambda prompt: "ONELINE: did the thing\nDETAIL: all good"
    one, full = generate_recap(p, ccrider_db, runner=fake)
    assert one == "did the thing"


def test_ensure_recaps_caches_and_reuses(tmp_path, ccrider_db):
    p = _project(ccrider_db, "regrade3")
    cache = RecapCache(tmp_path / "r.db")
    config = Config()
    calls = []
    def runner(prompt):
        calls.append(1)
        return "ONELINE: cached me\nDETAIL: x"
    r1 = ensure_recaps([p], ccrider_db, cache, config, runner=runner)
    r2 = ensure_recaps([p], ccrider_db, cache, config, runner=runner)  # signature unchanged -> cache hit
    assert r1["regrade3"][0] == "cached me"
    assert r2["regrade3"][0] == "cached me"
    assert len(calls) == 1
    cache.close()


def test_ensure_recaps_skips_llm_when_auth_mode_none(tmp_path, ccrider_db):
    p = _project(ccrider_db, "regrade3")
    cache = RecapCache(tmp_path / "r.db")
    config = Config(recap_auth_mode="none")
    calls = []
    def runner(prompt):
        calls.append(1)
        return "ONELINE: should not be called\nDETAIL: x"
    r = ensure_recaps([p], ccrider_db, cache, config, runner=runner)
    assert calls == []  # runner never invoked
    assert r["regrade3"][0].startswith("do the thing")  # derived fallback
    cache.close()


def test_ensure_recaps_falls_back_on_runner_error(tmp_path, ccrider_db):
    p = _project(ccrider_db, "regrade3")
    cache = RecapCache(tmp_path / "r.db")
    config = Config()
    def boom(prompt):
        raise RuntimeError("claude failed")
    r = ensure_recaps([p], ccrider_db, cache, config, runner=boom)
    assert r["regrade3"][0].startswith("do the thing")
    cache.close()


def test_claude_runner_runs_in_neutral_cwd(monkeypatch):
    captured = {}

    def fake_run(cmd, capture_output, text, env, timeout, cwd):
        captured["cwd"] = cwd
        captured["env"] = env
        class Result:
            returncode = 0
            stdout = "ONELINE: ok\nDETAIL: ok"
        return Result()

    monkeypatch.setattr("reconvene.recap.subprocess.run", fake_run)
    claude_runner("a prompt", Config())
    assert captured["cwd"] == tempfile.gettempdir()


def test_claude_runner_sets_api_key_when_configured(monkeypatch):
    captured = {}

    def fake_run(cmd, capture_output, text, env, timeout, cwd):
        captured["env"] = env
        class Result:
            returncode = 0
            stdout = "ONELINE: ok\nDETAIL: ok"
        return Result()

    monkeypatch.setattr("reconvene.recap.subprocess.run", fake_run)
    claude_runner("a prompt", Config(recap_auth_mode="api_key", api_key="sk-test"))
    assert captured["env"]["ANTHROPIC_API_KEY"] == "sk-test"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_recap.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'reconvene.recap'`

- [ ] **Step 3: Write minimal implementation**

```python
# reconvene/recap.py
# ABOUTME: Generates and caches per-project recaps from recent session transcripts via `claude -p`.
# ABOUTME: Cache is keyed by project + a signature of the included sessions so grown sessions refresh.
import hashlib
import os
import sqlite3
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .constants import MODEL, RECAP_CACHE_DB, RECAP_CONCURRENCY, RECENT_SESSIONS_FOR_RECAP
from .db import session_messages


def signature(sessions) -> str:
    parts = [f"{s.session_id}:{s.updated_at}:{s.message_count}" for s in sessions]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


class RecapCache:
    def __init__(self, path=RECAP_CACHE_DB):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS recaps "
            "(project TEXT PRIMARY KEY, signature TEXT, oneline TEXT, full TEXT)"
        )
        self.conn.commit()

    def get(self, project, sig):
        row = self.conn.execute(
            "SELECT oneline, full FROM recaps WHERE project=? AND signature=?",
            (project, sig),
        ).fetchone()
        return (row[0], row[1]) if row else None

    def put(self, project, sig, oneline, full):
        self.conn.execute(
            "INSERT INTO recaps(project,signature,oneline,full) VALUES(?,?,?,?) "
            "ON CONFLICT(project) DO UPDATE SET "
            "signature=excluded.signature, oneline=excluded.oneline, full=excluded.full",
            (project, sig, oneline, full),
        )
        self.conn.commit()

    def close(self):
        self.conn.close()


PROMPT_TEMPLATE = (
    "You are summarizing recent coding-agent sessions for the project '{name}' so the developer "
    "can decide whether to resume this thread. The sessions are newest-first.\n\n"
    "Respond in EXACTLY this format and nothing else:\n"
    "ONELINE: <one sentence, <=90 chars, what the project is currently about / last worked on>\n"
    "DETAIL: <2-4 short lines: what was done, current state, any obvious next step>\n\n"
    "{transcript}"
)


def build_prompt(project, db_path, recent=RECENT_SESSIONS_FOR_RECAP, per_session_chars=2000):
    blocks = []
    for s in project.sessions[:recent]:
        msgs = session_messages(db_path, s.session_id)
        text = "\n".join(f"{sender}: {body}" for sender, body in msgs)
        blocks.append(f"--- session {s.updated_at} ---\n{text[:per_session_chars]}")
    return PROMPT_TEMPLATE.format(name=project.name, transcript="\n\n".join(blocks))


def parse_recap(output: str) -> tuple[str, str]:
    oneline, detail = "", ""
    for line in output.splitlines():
        if line.startswith("ONELINE:"):
            oneline = line[len("ONELINE:"):].strip()
        elif line.startswith("DETAIL:"):
            detail = line[len("DETAIL:"):].strip()
        elif detail and line.strip():
            detail += "\n" + line.strip()
    if not oneline:
        first = next((l for l in output.splitlines() if l.strip()), "")
        oneline = first.strip()[:90]
    return oneline, (detail or oneline)


def first_user_message(db_path, session_id, limit=90) -> str:
    msgs = session_messages(db_path, session_id)
    first_user = next((body for sender, body in msgs if "user" in sender.lower()), "")
    return first_user.replace("\n", " ").strip()[:limit]


def derive_recap(project, db_path) -> tuple[str, str]:
    oneline = first_user_message(db_path, project.latest.session_id) or "(no recap)"
    return oneline, oneline


def claude_runner(prompt, config, model=MODEL, timeout=120) -> str:
    env = dict(os.environ)
    if config.recap_auth_mode == "api_key" and config.api_key:
        env["ANTHROPIC_API_KEY"] = config.api_key
    proc = subprocess.run(
        ["claude", "-p", "--model", model, prompt],
        capture_output=True, text=True, env=env, timeout=timeout,
        cwd=tempfile.gettempdir(),  # not the user's launch cwd — keeps this call out of their project history
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p failed: {proc.stderr.strip()[:200]}")
    return proc.stdout


def generate_recap(project, db_path, runner) -> tuple[str, str]:
    return parse_recap(runner(build_prompt(project, db_path)))


def ensure_recaps(projects, db_path, cache, config, runner=None, concurrency=RECAP_CONCURRENCY):
    use_llm = config.recap_auth_mode != "none"
    active_runner = runner or (lambda prompt: claude_runner(prompt, config))

    results: dict[str, tuple[str, str]] = {}
    todo = []
    for p in projects:
        sig = signature(p.sessions[:RECENT_SESSIONS_FOR_RECAP])
        hit = cache.get(p.name, sig)
        if hit:
            results[p.name] = hit
        else:
            todo.append((p, sig))

    def work(item):
        p, sig = item
        try:
            recap = generate_recap(p, db_path, active_runner) if use_llm else derive_recap(p, db_path)
        except Exception:
            try:
                recap = derive_recap(p, db_path)
            except Exception:
                recap = ("(recap failed)", "(recap failed)")
        return p.name, sig, recap

    if todo:
        with ThreadPoolExecutor(max_workers=concurrency) as ex:
            for name, sig, recap in ex.map(work, todo):
                cache.put(name, sig, recap[0], recap[1])
                results[name] = recap
    return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_recap.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add reconvene/recap.py tests/test_recap.py
git commit -m "feat: add recap generation with configurable auth mode and neutral cwd"
```

---

## Task 8: `resume.py`

**Files:**
- Create: `reconvene/resume.py`
- Test: `tests/test_resume.py`

**Interfaces:**
- Produces: `resume_command(session_id: str) -> list[str]`, `open_terminal_and_resume(session_id: str, cwd: str, runner=subprocess.run) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_resume.py
# ABOUTME: Tests for building the resume command and the macOS terminal-launch automation.
# ABOUTME: Injects a fake subprocess runner so no real Terminal window is ever opened in tests.
import pytest

from reconvene.resume import open_terminal_and_resume, resume_command


def test_resume_command():
    assert resume_command("abc123") == ["claude", "--resume", "abc123"]


def test_open_terminal_and_resume_runs_osascript():
    captured = {}
    def fake_runner(cmd, check):
        captured["cmd"] = cmd
        captured["check"] = check
    open_terminal_and_resume("abc123", "/Users/x/Code/regrade3", runner=fake_runner)
    assert captured["cmd"][0] == "osascript"
    assert captured["cmd"][1] == "-e"
    script = captured["cmd"][2]
    assert "Terminal" in script
    assert "/Users/x/Code/regrade3" in script
    assert "claude --resume abc123" in script
    assert captured["check"] is True


def test_open_terminal_and_resume_raises_on_failure():
    def failing_runner(cmd, check):
        raise RuntimeError("osascript not found")
    with pytest.raises(RuntimeError, match="osascript not found"):
        open_terminal_and_resume("abc123", "/Users/x/Code/regrade3", runner=failing_runner)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_resume.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'reconvene.resume'`

- [ ] **Step 3: Write minimal implementation**

```python
# reconvene/resume.py
# ABOUTME: Builds the argv that hands a chosen session back to Claude Code to resume.
# ABOUTME: open_terminal_and_resume opens a new macOS Terminal window (no execvp — the
# ABOUTME: caller is a web server that must keep running to serve other requests).
import shlex
import subprocess


def resume_command(session_id: str) -> list[str]:
    return ["claude", "--resume", session_id]


def open_terminal_and_resume(session_id: str, cwd: str, runner=subprocess.run) -> None:
    command = " ".join(resume_command(session_id))
    script = f'tell application "Terminal" to do script "cd {shlex.quote(cwd)} && {command}"'
    runner(["osascript", "-e", script], check=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_resume.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add reconvene/resume.py tests/test_resume.py
git commit -m "feat: add resume command builder and macOS terminal-launch automation"
```

---

## Task 9: Web server skeleton + journal API + static file serving

**Files:**
- Create: `reconvene/web/__init__.py`
- Create: `reconvene/web/server.py`
- Create: `reconvene/web/static/index.html`
- Create: `reconvene/web/static/style.css`
- Create: `reconvene/web/static/app.js`
- Test: `tests/test_web_server.py`

**Interfaces:**
- Consumes: `load_sessions` from `reconvene.db`; `build_journal` from `reconvene.journal`; `first_user_message` from `reconvene.recap`; `Config` from `reconvene.config`.
- Produces: `make_handler(config, db_path, cache_path, resumer) -> type[BaseHTTPRequestHandler]`, `serve(config, db_path, cache_path, resumer, host="127.0.0.1", port=0) -> ThreadingHTTPServer`. Routes so far: `GET /` (static index), `GET /style.css`, `GET /app.js` (static assets), `GET /api/journal` (JSON project list).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_web_server.py
# ABOUTME: Tests for the local HTTP server — routes tested via real HTTP requests
# ABOUTME: against a server instance running on a random free port in a background thread.
import json
import threading
import urllib.request
from urllib.error import HTTPError

import pytest

from reconvene.config import Config
from reconvene.web.server import serve
from tests.conftest import add_session, add_message


@pytest.fixture
def running_server(tmp_path, ccrider_db):
    add_session(ccrider_db, "r1", "/Users/x/Code/regrade3", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "r1", "user", "wire up thresholds", sequence=1)
    config = Config()
    resumed = []
    def fake_resumer(session_id, cwd):
        resumed.append((session_id, cwd))
    server = serve(config, str(ccrider_db), str(tmp_path / "recaps.db"), fake_resumer, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    yield base_url, resumed, config
    server.shutdown()
    server.server_close()


def test_index_serves_static_html(running_server):
    base_url, _, _ = running_server
    with urllib.request.urlopen(f"{base_url}/") as resp:
        assert resp.status == 200
        assert b"Reconvene" in resp.read()


def test_unknown_static_path_is_404(running_server):
    base_url, _, _ = running_server
    with pytest.raises(HTTPError) as exc:
        urllib.request.urlopen(f"{base_url}/no-such-file.html")
    assert exc.value.code == 404


def test_static_path_traversal_is_blocked(running_server):
    base_url, _, _ = running_server
    with pytest.raises(HTTPError) as exc:
        urllib.request.urlopen(f"{base_url}/../../../etc/passwd")
    assert exc.value.code == 404


def test_api_journal_returns_ranked_projects(running_server):
    base_url, _, _ = running_server
    with urllib.request.urlopen(f"{base_url}/api/journal") as resp:
        data = json.loads(resp.read())
    assert data["real"][0]["name"] == "regrade3"
    assert data["real"][0]["latest_session_id"] == "r1"
    assert "wire up thresholds" in data["real"][0]["oneline"]
    assert data["bots"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_web_server.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'reconvene.web'`

- [ ] **Step 3: Write minimal implementation**

```python
# reconvene/web/__init__.py
```

```html
<!-- reconvene/web/static/index.html -->
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Reconvene</title>
  <link rel="stylesheet" href="/style.css">
</head>
<body>
  <h1>Reconvene</h1>
  <div id="journal">Loading…</div>
  <a href="/settings.html">Settings</a>
  <script src="/app.js"></script>
</body>
</html>
```

```css
/* reconvene/web/static/style.css */
body { font-family: system-ui, sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; }
.project { border: 1px solid #ccc; border-radius: 6px; padding: 0.75rem 1rem; margin-bottom: 0.5rem; cursor: pointer; }
.project:hover { background: #f5f5f5; }
.project .meta { color: #666; font-size: 0.85rem; }
.error { background: #fdecea; color: #611a15; border: 1px solid #f5c6cb; border-radius: 6px; padding: 0.5rem 0.75rem; margin-bottom: 1rem; }
```

```javascript
// reconvene/web/static/app.js
function showError(message) {
  let el = document.getElementById("error");
  if (!el) {
    el = document.createElement("div");
    el.id = "error";
    el.className = "error";
    document.body.insertBefore(el, document.getElementById("journal"));
  }
  el.textContent = message;
}

async function loadJournal() {
  const res = await fetch("/api/journal");
  const data = await res.json();
  const el = document.getElementById("journal");
  el.innerHTML = "";
  for (const project of data.real) {
    const div = document.createElement("div");
    div.className = "project";
    div.dataset.sessionId = project.latest_session_id;
    div.innerHTML = `<strong>${project.name}</strong> · ${project.count} sessions
      <div class="meta">${project.oneline}</div>`;
    div.addEventListener("click", () => resumeProject(project.latest_session_id));
    el.appendChild(div);
  }
}

async function resumeProject(sessionId) {
  const res = await fetch(`/api/resume/${sessionId}`, { method: "POST" });
  if (!res.ok) {
    const data = await res.json();
    showError(`Couldn't resume: ${data.error}`);
  }
}

loadJournal();
```

```python
# reconvene/web/server.py
# ABOUTME: Local HTTP server for Reconvene — a small JSON API plus static file serving.
# ABOUTME: Bound to 127.0.0.1 only; never exposed to the network.
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from ..db import load_sessions
from ..journal import build_journal
from ..recap import first_user_message

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _project_summary(p, db_path):
    return {
        "name": p.name,
        "category": p.category,
        "count": p.count,
        "last_active": p.last_active,
        "latest_session_id": p.latest.session_id,
        "oneline": first_user_message(db_path, p.latest.session_id) or "(no recap)",
    }


def make_handler(config, db_path, cache_path, resumer):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass  # keep test/CLI output quiet

        def _send_json(self, status, payload):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_static(self, rel_path):
            file_path = (STATIC_DIR / rel_path).resolve()
            try:
                file_path.relative_to(STATIC_DIR.resolve())
            except ValueError:
                self.send_response(404)
                self.end_headers()
                return
            if not file_path.is_file():
                self.send_response(404)
                self.end_headers()
                return
            content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
            body = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/api/journal":
                sessions = load_sessions(db_path)
                real, bots = build_journal(sessions, config)
                self._send_json(200, {
                    "real": [_project_summary(p, db_path) for p in real],
                    "bots": [_project_summary(p, db_path) for p in bots],
                })
                return
            rel_path = "index.html" if path == "/" else path.lstrip("/")
            self._send_static(rel_path)

    return Handler


def serve(config, db_path, cache_path, resumer, host="127.0.0.1", port=0):
    handler = make_handler(config, db_path, cache_path, resumer)
    return ThreadingHTTPServer((host, port), handler)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_web_server.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add reconvene/web/__init__.py reconvene/web/server.py reconvene/web/static tests/test_web_server.py
git commit -m "feat: add web server skeleton with journal API and static file serving"
```

---

## Task 10: Resume endpoint

**Files:**
- Modify: `reconvene/web/server.py` (add `do_POST`)
- Test: `tests/test_web_server.py` (append tests)

**Interfaces:**
- Consumes: `resumer(session_id: str, project_path: str) -> None` (injected dependency, e.g. `open_terminal_and_resume`).
- Produces: `POST /api/resume/<session_id>` route.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_web_server.py`:

```python
def test_resume_calls_resumer_with_session_and_path(running_server):
    base_url, resumed, _ = running_server
    req = urllib.request.Request(f"{base_url}/api/resume/r1", method="POST", data=b"")
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    assert data["status"] == "resumed"
    assert resumed == [("r1", "/Users/x/Code/regrade3")]


def test_resume_unknown_session_is_404(running_server):
    base_url, resumed, _ = running_server
    req = urllib.request.Request(f"{base_url}/api/resume/does-not-exist", method="POST", data=b"")
    with pytest.raises(HTTPError) as exc:
        urllib.request.urlopen(req)
    assert exc.value.code == 404
    assert resumed == []


def test_resume_resumer_failure_returns_500(tmp_path, ccrider_db):
    add_session(ccrider_db, "r1", "/Users/x/Code/regrade3", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "r1", "user", "wire up thresholds", sequence=1)
    config = Config()
    def failing_resumer(session_id, cwd):
        raise RuntimeError("osascript not found")
    server = serve(config, str(ccrider_db), str(tmp_path / "recaps.db"), failing_resumer, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        req = urllib.request.Request(f"{base_url}/api/resume/r1", method="POST", data=b"")
        with pytest.raises(HTTPError) as exc:
            urllib.request.urlopen(req)
        assert exc.value.code == 500
    finally:
        server.shutdown()
        server.server_close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_web_server.py -v`
Expected: FAIL — `test_resume_calls_resumer_with_session_and_path` and related tests fail with 404 (no `do_POST` handler defined, `BaseHTTPRequestHandler` default returns 501 for unimplemented methods).

- [ ] **Step 3: Write minimal implementation**

In `reconvene/web/server.py`, add `do_POST` to the `Handler` class (inside `make_handler`, after `do_GET`):

```python
        def do_POST(self):
            path = urlparse(self.path).path
            if path.startswith("/api/resume/"):
                session_id = path[len("/api/resume/"):]
                sessions = load_sessions(db_path)
                real, bots = build_journal(sessions, config)
                match = next(
                    (s for p in real + bots for s in p.sessions if s.session_id == session_id),
                    None,
                )
                if match is None:
                    self._send_json(404, {"error": f"no session {session_id!r}"})
                    return
                try:
                    resumer(session_id, match.project_path)
                except Exception as e:
                    self._send_json(500, {"error": str(e)})
                    return
                self._send_json(200, {"status": "resumed"})
                return
            self.send_response(404)
            self.end_headers()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_web_server.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add reconvene/web/server.py tests/test_web_server.py
git commit -m "feat: add resume endpoint with error surfacing on resumer failure"
```

---

## Task 11: Recap endpoint (async fill-in)

**Files:**
- Modify: `reconvene/web/server.py` (add `/api/recap/<name>` to `do_GET`)
- Modify: `reconvene/web/static/app.js` (fetch full recap per card)
- Test: `tests/test_web_server.py` (append tests)

**Interfaces:**
- Consumes: `RecapCache`, `ensure_recaps` from `reconvene.recap`.
- Produces: `GET /api/recap/<project_name>` route returning `{"oneline": str, "full": str}`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_web_server.py`:

```python
def test_recap_endpoint_returns_derived_recap_without_llm(running_server):
    # running_server's Config() defaults to recap_auth_mode="claude_cli", but no real
    # `claude` binary is invoked here because we only exercise the endpoint's plumbing
    # with a project whose session is short enough that ensure_recaps' fallback chain
    # applies if the real claude_runner errors (no `claude` on the test machine's PATH
    # is not guaranteed, so assert on structure, not exact content).
    base_url, _, _ = running_server
    with urllib.request.urlopen(f"{base_url}/api/recap/regrade3") as resp:
        data = json.loads(resp.read())
    assert "oneline" in data
    assert "full" in data


def test_recap_endpoint_unknown_project_is_404(running_server):
    base_url, _, _ = running_server
    with pytest.raises(HTTPError) as exc:
        urllib.request.urlopen(f"{base_url}/api/recap/does-not-exist")
    assert exc.value.code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_web_server.py -v`
Expected: FAIL — `/api/recap/regrade3` currently falls through to static file serving and 404s.

- [ ] **Step 3: Write minimal implementation**

In `reconvene/web/server.py`, add the import and route. First, update imports at the top:

```python
from ..recap import RecapCache, ensure_recaps, first_user_message
```

(replacing the previous `from ..recap import first_user_message` line).

Then in `do_GET`, add a branch before the static-file fallback:

```python
            if path.startswith("/api/recap/"):
                name = path[len("/api/recap/"):]
                sessions = load_sessions(db_path)
                real, bots = build_journal(sessions, config)
                project = next((p for p in real + bots if p.name == name), None)
                if project is None:
                    self._send_json(404, {"error": f"no project named {name!r}"})
                    return
                cache = RecapCache(cache_path)
                try:
                    recaps = ensure_recaps([project], db_path, cache, config)
                finally:
                    cache.close()
                oneline, full = recaps.get(project.name, ("", "(no recap)"))
                self._send_json(200, {"oneline": oneline, "full": full})
                return
```

Update `reconvene/web/static/app.js`'s `loadJournal` to fetch the full recap per card after the initial render:

```javascript
async function loadJournal() {
  const res = await fetch("/api/journal");
  const data = await res.json();
  const el = document.getElementById("journal");
  el.innerHTML = "";
  for (const project of data.real) {
    const div = document.createElement("div");
    div.className = "project";
    div.dataset.sessionId = project.latest_session_id;
    const metaEl = document.createElement("div");
    metaEl.className = "meta";
    metaEl.textContent = project.oneline;
    div.innerHTML = `<strong>${project.name}</strong> · ${project.count} sessions`;
    div.appendChild(metaEl);
    div.addEventListener("click", () => resumeProject(project.latest_session_id));
    el.appendChild(div);
    fetch(`/api/recap/${project.name}`)
      .then((r) => r.json())
      .then((recap) => { metaEl.textContent = recap.oneline; });
  }
}

async function resumeProject(sessionId) {
  const res = await fetch(`/api/resume/${sessionId}`, { method: "POST" });
  if (!res.ok) {
    const data = await res.json();
    showError(`Couldn't resume: ${data.error}`);
  }
}

loadJournal();
```

(`showError`, defined in Task 9's version of this file, is unchanged and still present above these functions.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_web_server.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add reconvene/web/server.py reconvene/web/static/app.js tests/test_web_server.py
git commit -m "feat: add async recap endpoint, fill in full recap per card client-side"
```

---

## Task 12: Settings endpoint and page

**Files:**
- Modify: `reconvene/web/server.py` (add `/api/settings` to both `do_GET` and `do_POST`)
- Create: `reconvene/web/static/settings.html`
- Create: `reconvene/web/static/settings.js`
- Test: `tests/test_web_server.py` (append tests)

**Interfaces:**
- Consumes: `save_config` from `reconvene.config`.
- Produces: `GET /api/settings` (JSON: all classified projects + current config), `POST /api/settings` (accepts JSON body, saves overrides, returns updated config).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_web_server.py`:

```python
def test_settings_get_lists_projects_and_config(running_server):
    base_url, _, _ = running_server
    with urllib.request.urlopen(f"{base_url}/api/settings") as resp:
        data = json.loads(resp.read())
    assert any(p["name"] == "regrade3" for p in data["projects"])
    assert data["config"]["recap_auth_mode"] == "claude_cli"


def test_settings_post_saves_overrides(tmp_path, ccrider_db):
    add_session(ccrider_db, "r1", "/Users/x/Code/regrade3", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "r1", "user", "wire up thresholds", sequence=1)
    config = Config()
    server = serve(config, str(ccrider_db), str(tmp_path / "recaps.db"), lambda s, c: None, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        payload = json.dumps({
            "bot_names": ["regrade3"],
            "hidden_names": [],
            "recap_auth_mode": "none",
            "api_key": None,
        }).encode()
        req = urllib.request.Request(f"{base_url}/api/settings", method="POST", data=payload,
                                      headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
        assert data["status"] == "saved"
        assert config.bot_names == {"regrade3"}
        assert config.recap_auth_mode == "none"
    finally:
        server.shutdown()
        server.server_close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_web_server.py -v`
Expected: FAIL — `/api/settings` 404s on both GET and POST (no route defined yet).

- [ ] **Step 3: Write minimal implementation**

In `reconvene/web/server.py`, update the import line to add `save_config`:

```python
from ..config import save_config
```

Add a branch in `do_GET` (before the static-file fallback):

```python
            if path == "/api/settings":
                sessions = load_sessions(db_path)
                real, bots = build_journal(sessions, config)
                self._send_json(200, {
                    "projects": [_project_summary(p, db_path) for p in real + bots],
                    "config": config.to_dict(),
                })
                return
```

Add a branch in `do_POST` (before the final 404 fallback), and read the request body at the top of `do_POST`:

```python
        def do_POST(self):
            path = urlparse(self.path).path
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b"{}"
            if path.startswith("/api/resume/"):
                session_id = path[len("/api/resume/"):]
                sessions = load_sessions(db_path)
                real, bots = build_journal(sessions, config)
                match = next(
                    (s for p in real + bots for s in p.sessions if s.session_id == session_id),
                    None,
                )
                if match is None:
                    self._send_json(404, {"error": f"no session {session_id!r}"})
                    return
                try:
                    resumer(session_id, match.project_path)
                except Exception as e:
                    self._send_json(500, {"error": str(e)})
                    return
                self._send_json(200, {"status": "resumed"})
                return
            if path == "/api/settings":
                data = json.loads(body)
                config.bot_names = set(data.get("bot_names", []))
                config.hidden_names = set(data.get("hidden_names", []))
                config.recap_auth_mode = data.get("recap_auth_mode", config.recap_auth_mode)
                config.api_key = data.get("api_key", config.api_key)
                save_config(config)
                self._send_json(200, {"status": "saved", "config": config.to_dict()})
                return
            self.send_response(404)
            self.end_headers()
```

This replaces the entire `do_POST` method added in Task 10 — the `/api/resume/` branch is unchanged from Task 10, shown here in full (not abbreviated) since the engineer implementing this task may not have Task 10's diff in view. Only the `length`/`body` lines and the new `/api/settings` branch are additions.

Create `reconvene/web/static/settings.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Reconvene — Settings</title>
  <link rel="stylesheet" href="/style.css">
</head>
<body>
  <h1>Settings</h1>
  <table id="projects"></table>
  <h2>Recap generation</h2>
  <label><input type="radio" name="auth" value="claude_cli"> Use claude CLI login</label><br>
  <label><input type="radio" name="auth" value="api_key"> Use an API key</label>
  <input type="text" id="apiKey" placeholder="sk-..."><br>
  <label><input type="radio" name="auth" value="none"> No recaps</label><br>
  <button id="save">Save</button>
  <a href="/">Back</a>
  <script src="/settings.js"></script>
</body>
</html>
```

Create `reconvene/web/static/settings.js`:

```javascript
let projects = [];

async function loadSettings() {
  const res = await fetch("/api/settings");
  const data = await res.json();
  projects = data.projects;
  const table = document.getElementById("projects");
  table.innerHTML = "";
  for (const p of projects) {
    const row = document.createElement("tr");
    row.innerHTML = `<td>${p.name}</td><td>
      <select data-name="${p.name}">
        <option value="real" ${p.category === "real" ? "selected" : ""}>Real</option>
        <option value="bot" ${p.category === "bot" ? "selected" : ""}>Automated</option>
        <option value="drop" ${p.category === "drop" ? "selected" : ""}>Hidden</option>
      </select></td>`;
    table.appendChild(row);
  }
  const authRadio = document.querySelector(`input[name="auth"][value="${data.config.recap_auth_mode}"]`);
  if (authRadio) authRadio.checked = true;
  document.getElementById("apiKey").value = data.config.api_key || "";
}

document.getElementById("save").addEventListener("click", async () => {
  const botNames = [];
  const hiddenNames = [];
  for (const select of document.querySelectorAll("#projects select")) {
    if (select.value === "bot") botNames.push(select.dataset.name);
    if (select.value === "drop") hiddenNames.push(select.dataset.name);
  }
  const authMode = document.querySelector('input[name="auth"]:checked').value;
  await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      bot_names: botNames,
      hidden_names: hiddenNames,
      recap_auth_mode: authMode,
      api_key: document.getElementById("apiKey").value || null,
    }),
  });
});

loadSettings();
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_web_server.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add reconvene/web/server.py reconvene/web/static/settings.html reconvene/web/static/settings.js tests/test_web_server.py
git commit -m "feat: add settings endpoint and page for classification overrides"
```

---

## Task 13: CLI entry point wiring it all together

**Files:**
- Create: `reconvene/cli.py`
- Modify: `README.md` (usage instructions)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `load_config` from `reconvene.config`; `serve` from `reconvene.web.server`; `open_terminal_and_resume` from `reconvene.resume`; `CCRIDER_DB`, `RECAP_CACHE_DB` from `reconvene.constants`.
- Produces: `main(argv=None) -> int`, `find_free_port(preferred=4242, tries=10) -> int`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py
# ABOUTME: Tests for the CLI entry point's port selection, argument handling, and
# ABOUTME: startup error paths (missing ccrider binary, no free port available).
import socket

import pytest

from reconvene import cli
from reconvene.cli import find_free_port


def test_find_free_port_returns_preferred_when_available():
    port = find_free_port(preferred=47001, tries=5)
    assert port == 47001


def test_find_free_port_skips_occupied_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 47002))
    sock.listen(1)
    try:
        port = find_free_port(preferred=47002, tries=5)
        assert port != 47002
    finally:
        sock.close()


def test_find_free_port_raises_when_none_available():
    sockets = []
    try:
        for offset in range(3):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(("127.0.0.1", 47010 + offset))
            sock.listen(1)
            sockets.append(sock)
        with pytest.raises(RuntimeError, match="no free port"):
            find_free_port(preferred=47010, tries=3)
    finally:
        for sock in sockets:
            sock.close()


def test_main_prints_clear_error_when_ccrider_missing(monkeypatch, capsys):
    def fake_run(cmd):
        raise FileNotFoundError("no such file: ccrider")
    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    rc = cli.main([])
    assert rc == 1
    assert "brew install neilberkman/tap/ccrider" in capsys.readouterr().err


def test_main_prints_clear_error_when_no_port_available(monkeypatch, capsys):
    monkeypatch.setattr(cli, "find_free_port", lambda: (_ for _ in ()).throw(RuntimeError("no free port found in range 4242-4251")))
    rc = cli.main(["--no-sync"])
    assert rc == 1
    assert "no free port found" in capsys.readouterr().err
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'reconvene.cli'`

- [ ] **Step 3: Write minimal implementation**

```python
# reconvene/cli.py
# ABOUTME: CLI entry point — syncs ccrider, starts the local web server, opens the browser.
import argparse
import socket
import subprocess
import sys
import threading
import webbrowser

from .config import load_config
from .constants import CCRIDER_DB, RECAP_CACHE_DB, VERSION
from .resume import open_terminal_and_resume
from .web.server import serve


def find_free_port(preferred=4242, tries=10) -> int:
    for offset in range(tries):
        candidate = preferred + offset
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("127.0.0.1", candidate))
            return candidate
        except OSError:
            continue
        finally:
            sock.close()
    raise RuntimeError(f"no free port found in range {preferred}-{preferred + tries - 1}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="reconvene", description="Resume a Claude Code project by its journal.")
    ap.add_argument("--no-sync", action="store_true", help="skip `ccrider sync` first")
    ap.add_argument("--db", default=str(CCRIDER_DB), help="ccrider sessions DB path")
    ap.add_argument("--cache", default=str(RECAP_CACHE_DB), help="recap cache path")
    ap.add_argument("-V", "--version", action="version", version=f"reconvene {VERSION}")
    args = ap.parse_args(argv)

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

    config = load_config()
    try:
        port = find_free_port()
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    server = serve(config, args.db, args.cache, open_terminal_and_resume, port=port)
    url = f"http://127.0.0.1:{port}"
    print(f"Reconvene running at {url}")
    threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Write `README.md`**

```markdown
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
```

- [ ] **Step 6: Commit**

```bash
git add reconvene/cli.py tests/test_cli.py README.md
git commit -m "feat: add CLI entry point, port selection, and README"
```

---

## Task 14: End-to-end test

**Files:**
- Create: `tests/test_e2e.py`

**Interfaces:**
- Consumes: everything above. No new interfaces produced — this is a full-stack verification task.

- [ ] **Step 1: Write the test**

```python
# tests/test_e2e.py
# ABOUTME: End-to-end test exercising the full stack: DB -> journal -> web API -> resume,
# ABOUTME: with a fake resumer (never actually opens a Terminal window in tests).
import json
import threading
import urllib.request

from reconvene.config import Config, save_config
from reconvene.web.server import serve
from tests.conftest import add_session, add_message


def test_full_journal_and_resume_flow(tmp_path, ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-01 00:00:00", message_count=40)
    add_message(ccrider_db, "s1", "user", "build the thing", sequence=1)
    add_session(ccrider_db, "s2", "/Users/x/Code/scoutbot", "2026-07-02 00:00:00", message_count=2)
    add_message(ccrider_db, "s2", "user", "score this idea", sequence=1)

    config_path = tmp_path / "config.json"
    config = Config(bot_names={"scoutbot"})
    save_config(config, config_path)

    resumed = []
    server = serve(config, str(ccrider_db), str(tmp_path / "recaps.db"),
                    lambda sid, cwd: resumed.append((sid, cwd)), port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"

        with urllib.request.urlopen(f"{base_url}/api/journal") as resp:
            journal = json.loads(resp.read())
        assert [p["name"] for p in journal["real"]] == ["myproject"]
        assert [p["name"] for p in journal["bots"]] == ["scoutbot"]

        req = urllib.request.Request(f"{base_url}/api/resume/s1", method="POST", data=b"")
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
        assert result["status"] == "resumed"
        assert resumed == [("s1", "/Users/x/Code/myproject")]
    finally:
        server.shutdown()
        server.server_close()
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/test_e2e.py -v`
Expected: PASS (1 test)

- [ ] **Step 3: Run the full suite**

Run: `pytest tests/ -v`
Expected: All tests pass (should be around 45 tests total across all modules)

- [ ] **Step 4: Commit**

```bash
git add tests/test_e2e.py
git commit -m "test: add end-to-end journal and resume flow test"
```
