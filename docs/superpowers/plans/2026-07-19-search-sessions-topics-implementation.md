# Search, Per-Session Resume, and Topic Clustering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Full-text session search (via ccrider's existing FTS5 index), drill-in resume of any specific session, and sticky LLM topic clustering of sessions launched from root directories like `~/Code` — in both the web GUI and the fzf TUI.

**Architecture:** A new `search.py` queries ccrider's `messages_fts` FTS5 table read-only. A new `cluster.py` detects "root" launch paths automatically and stores permanent `session_id → topic` assignments in the reconvene cache DB; journal grouping consumes them. The web server gains `/api/search`, `/api/sessions/<name>`, `/api/topics/refresh`; the TUI gains a tuple-returning picker protocol (`--expect`), a second-level session picker, and a live FTS search mode (`--disabled` + `change:reload`).

**Tech Stack:** Python 3.11+ stdlib only (sqlite3, subprocess, argparse). External CLIs: fzf, claude. Tests: pytest + Playwright (existing `.venv`).

## Global Constraints

- Python 3.11+ **stdlib only**; no new runtime dependencies.
- ccrider's DB is opened **read-only** (`file:…?mode=ro`) — never write to it.
- Snippet match markers are `«` and `»` (spec §1).
- Query sanitization: split on whitespace, strip `"` from tokens, wrap each token in double quotes, join with spaces (spec §1). Empty result → return `[]`.
- Missing `messages_fts` → `RuntimeError` naming the table; **no silent LIKE fallback**.
- Search results are NOT filtered by classification (dropped/hidden/bot sessions are findable).
- Journal loads NEVER call claude for clustering; organize is explicit (button / `--organize`).
- Topic assignments are sticky: `INSERT OR IGNORE` — an existing assignment is never overwritten.
- Root detection: path P (rstripped `/`) is a root when ≥3 distinct other session paths start with `P + "/"`, excluding children whose relative part contains any `WORKTREE_MARKERS` entry.
- Fallback group name: `abbreviate_home(root) + " (loose sessions)"`.
- All code files start with two `ABOUTME:` comment lines.
- Tests via `.venv/bin/python -m pytest`; TDD (write failing test → run → implement → run) per task.
- E2E tests need `PLAYWRIGHT_BROWSERS_PATH=$(pwd)/.playwright-browsers` (see README).

---

### Task 1: FTS5 test fixture + search core

**Files:**
- Modify: `tests/conftest.py` (add `messages_fts` to the fixture schema; populate in `add_message`)
- Create: `reconvene/search.py`
- Test: `tests/test_search.py`

**Interfaces:**
- Consumes: `reconvene.db._connect(db_path)` (read-only connection, `sqlite3.Row` rows).
- Produces: `SearchHit(session_id, project_path, updated_at, message_count, hits, snippet)` frozen dataclass; `sanitize_query(query) -> str`; `search_sessions(db_path, query, limit=30) -> list[SearchHit]`; constants `SNIPPET_OPEN = "«"`, `SNIPPET_CLOSE = "»"`. Tasks 2, 6, 8 rely on these exact names.

- [ ] **Step 1: Extend the fixture — add the FTS table and populate it**

In `tests/conftest.py`, inside the `ccrider_db` fixture's `executescript`, append after the `messages` table:

```sql
        CREATE VIRTUAL TABLE messages_fts USING fts5(
          text_content,
          content=messages,
          content_rowid=id,
          tokenize='porter unicode61'
        );
```

(FTS5 "external content" table: it indexes `messages.text_content` but stores no copy; with external content, inserts must be mirrored manually — ccrider does this in its sync, our fixture does it in `add_message`.)

Replace `add_message` with:

```python
def add_message(db, session_id, role, body, sequence, is_sidechain=0):
    sender = "human" if role == "user" else role
    conn = sqlite3.connect(db)
    cur = conn.execute(
        "INSERT INTO messages(session_id,type,sender,content,text_content,is_sidechain,sequence)"
        " VALUES((SELECT id FROM sessions WHERE session_id=?),?,?,?,?,?,?)",
        (session_id, role, sender, body, body, is_sidechain, sequence),
    )
    conn.execute(
        "INSERT INTO messages_fts(rowid, text_content) VALUES (?, ?)",
        (cur.lastrowid, body),
    )
    conn.commit()
    conn.close()
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_search.py`:

```python
# ABOUTME: Tests for FTS5-backed session search — sanitization, ranking, snippets, errors.
# ABOUTME: Runs against the fixture's real FTS5 external-content table (porter stemming included).
import sqlite3

import pytest

from reconvene.search import SNIPPET_CLOSE, SNIPPET_OPEN, sanitize_query, search_sessions
from tests.conftest import add_session, add_message


def test_sanitize_quotes_each_token():
    assert sanitize_query("pi-hole nas") == '"pi-hole" "nas"'


def test_sanitize_strips_embedded_quotes():
    assert sanitize_query('drop "tables" now') == '"drop" "tables" "now"'


def test_sanitize_empty_and_whitespace():
    assert sanitize_query("") == ""
    assert sanitize_query("   ") == ""


def test_search_empty_query_returns_no_hits(ccrider_db):
    assert search_sessions(str(ccrider_db), "   ") == []


def test_search_ranks_by_hit_count(ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/alpha", "2026-07-08 00:00:00", message_count=5)
    add_message(ccrider_db, "s1", "user", "pihole once", sequence=1)
    add_session(ccrider_db, "s2", "/Users/x/Code/beta", "2026-07-01 00:00:00", message_count=5)
    add_message(ccrider_db, "s2", "user", "pihole here", sequence=1)
    add_message(ccrider_db, "s2", "assistant", "pihole again", sequence=2)
    hits = search_sessions(str(ccrider_db), "pihole")
    assert [h.session_id for h in hits] == ["s2", "s1"]
    assert hits[0].hits == 2 and hits[1].hits == 1


def test_search_snippet_wraps_matches_in_markers(ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/alpha", "2026-07-08 00:00:00", message_count=5)
    add_message(ccrider_db, "s1", "user", "tuning the synology nas today", sequence=1)
    (hit,) = search_sessions(str(ccrider_db), "synology")
    assert f"{SNIPPET_OPEN}synology{SNIPPET_CLOSE}" in hit.snippet


def test_search_uses_porter_stemming(ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/alpha", "2026-07-08 00:00:00", message_count=5)
    add_message(ccrider_db, "s1", "user", "cleaning the desktop", sequence=1)
    assert len(search_sessions(str(ccrider_db), "cleaned")) == 1


def test_search_missing_fts_table_raises_clear_error(tmp_path):
    raw = tmp_path / "nofts.db"
    conn = sqlite3.connect(raw)
    conn.executescript(
        "CREATE TABLE sessions (id INTEGER PRIMARY KEY, session_id TEXT, project_path TEXT,"
        " summary TEXT, llm_summary TEXT, created_at TEXT, updated_at TEXT, message_count INT);"
        "CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id INT, text_content TEXT);"
    )
    conn.close()
    with pytest.raises(RuntimeError, match="messages_fts"):
        search_sessions(str(raw), "anything")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_search.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'reconvene.search'`

- [ ] **Step 4: Implement `reconvene/search.py`**

```python
# ABOUTME: Full-text session search over ccrider's messages_fts FTS5 index (read-only).
# ABOUTME: Sanitizes queries into quoted-token AND form so FTS5 syntax errors are impossible.
import sqlite3
from dataclasses import dataclass

from .db import _connect

SNIPPET_OPEN = "«"
SNIPPET_CLOSE = "»"


@dataclass(frozen=True)
class SearchHit:
    session_id: str
    project_path: str
    updated_at: str
    message_count: int
    hits: int
    snippet: str


def sanitize_query(query: str) -> str:
    # Each whitespace token becomes a quoted FTS5 string ("pi-hole" "nas" = implicit AND).
    # Quoting disables all FTS5 operator syntax, so user input can never cause a parse error;
    # porter stemming still applies inside quoted strings.
    tokens = [t.replace('"', "") for t in query.split()]
    return " ".join(f'"{t}"' for t in tokens if t)


def search_sessions(db_path, query, limit=30) -> list[SearchHit]:
    match = sanitize_query(query)
    if not match:
        return []
    conn = _connect(db_path)
    try:
        try:
            rows = conn.execute(
                "SELECT s.session_id, s.project_path, s.updated_at, s.message_count, "
                "count(*) AS hits, "
                "snippet(messages_fts, 0, ?, ?, '…', 10) AS snip "
                "FROM messages_fts "
                "JOIN messages m ON m.id = messages_fts.rowid "
                "JOIN sessions s ON s.id = m.session_id "
                "WHERE messages_fts MATCH ? "
                "GROUP BY s.id ORDER BY hits DESC, s.updated_at DESC LIMIT ?",
                (SNIPPET_OPEN, SNIPPET_CLOSE, match, limit),
            ).fetchall()
        except sqlite3.OperationalError as e:
            if "messages_fts" in str(e):
                raise RuntimeError(
                    "ccrider database has no messages_fts full-text index — "
                    "run `ccrider sync`, or ccrider's schema changed"
                ) from e
            raise
    finally:
        conn.close()
    return [
        SearchHit(r["session_id"], r["project_path"], r["updated_at"],
                  r["message_count"] or 0, r["hits"], r["snip"])
        for r in rows
    ]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_search.py -q` → all pass.
Then the full suite (the fixture changed): `.venv/bin/python -m pytest tests/ -q --ignore=tests/e2e` → all pass.

- [ ] **Step 6: Commit**

```bash
git add tests/conftest.py tests/test_search.py reconvene/search.py
git commit -m "feat: FTS5 session search core over ccrider's messages_fts"
```

---

### Task 2: `/api/search` endpoint + resume any session id

**Files:**
- Modify: `reconvene/web/server.py` (new GET route; rework `/api/resume/` lookup)
- Test: `tests/test_web_server.py`

**Interfaces:**
- Consumes: `search_sessions` (Task 1), `canonical_name` (`reconvene.classify`), `relative_time`/`abbreviate_home` (`reconvene.journal`).
- Produces: `GET /api/search?q=…` → `{"results": [{session_id, project, cwd, updated_at, relative, message_count, hits, snippet}]}`; `POST /api/resume/<sid>` now resumes ANY session in the DB (not just journal-visible ones). Tasks 3 and 5 rely on both.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_web_server.py`)

```python
def test_api_search_returns_session_hits(running_server, ccrider_db):
    base_url, _, _ = running_server
    add_session(ccrider_db, "s9", "/Users/x/Code/netstuff", "2026-07-09 00:00:00", message_count=8)
    add_message(ccrider_db, "s9", "user", "set up pihole dns blocking", sequence=1)
    with urllib.request.urlopen(f"{base_url}/api/search?q=pihole") as resp:
        data = json.loads(resp.read())
    (hit,) = data["results"]
    assert hit["session_id"] == "s9"
    assert hit["project"] == "netstuff"
    assert hit["hits"] == 1
    assert "«pihole»" in hit["snippet"]
    assert hit["cwd"] == "/Users/x/Code/netstuff"  # not under the test runner's real $HOME


def test_api_search_empty_query_returns_empty(running_server):
    base_url, _, _ = running_server
    with urllib.request.urlopen(f"{base_url}/api/search?q=") as resp:
        assert json.loads(resp.read()) == {"results": []}


def test_api_resume_works_for_unclassified_sessions(running_server, ccrider_db):
    # A 2-message session is noise-dropped from the journal, but search can surface it,
    # so resume must find it too.
    base_url, resumed, _ = running_server
    add_session(ccrider_db, "tiny", "/Users/x/Code/scratchpaddy", "2026-07-09 00:00:00", message_count=2)
    add_message(ccrider_db, "tiny", "user", "quick thing", sequence=1)
    req = urllib.request.Request(f"{base_url}/api/resume/tiny", method="POST")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
    assert resumed == [("tiny", "/Users/x/Code/scratchpaddy", "2026-07-09 00:00:00")]
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_web_server.py -q`
Expected: the three new tests FAIL (404s / HTTPError).

- [ ] **Step 3: Implement**

In `reconvene/web/server.py`:

Top of file — extend imports:

```python
from urllib.parse import parse_qs, unquote, urlparse

from ..classify import canonical_name
from ..search import search_sessions
```

In `do_GET`, after the `/api/settings` block and before the static fallback:

```python
            if path == "/api/search":
                q = parse_qs(urlparse(self.path).query).get("q", [""])[0]
                try:
                    hits = search_sessions(db_path, q)
                except RuntimeError as e:
                    self._send_json(500, {"error": str(e)})
                    return
                self._send_json(200, {"results": [
                    {
                        "session_id": h.session_id,
                        "project": canonical_name(h.project_path),
                        "cwd": abbreviate_home(h.project_path),
                        "updated_at": h.updated_at,
                        "relative": relative_time(h.updated_at),
                        "message_count": h.message_count,
                        "hits": h.hits,
                        "snippet": h.snippet,
                    }
                    for h in hits
                ]})
                return
```

In `do_POST`, replace the `/api/resume/` session lookup (currently a journal walk) with a raw-DB lookup:

```python
            if path.startswith("/api/resume/"):
                session_id = path[len("/api/resume/"):]
                match = next(
                    (s for s in load_sessions(db_path) if s.session_id == session_id),
                    None,
                )
```

(The rest of the block — 404, resumer call, error handling — is unchanged.)

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_web_server.py -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add reconvene/web/server.py tests/test_web_server.py
git commit -m "feat: /api/search endpoint; resume any session id"
```

---

### Task 3: Web search UI

**Files:**
- Modify: `reconvene/web/static/index.html` (topbar search input)
- Modify: `reconvene/web/static/app.js` (debounced search, results rendering, session modal)
- Modify: `reconvene/web/static/style.css` (search box + hit highlight styles)
- Test: `tests/e2e/test_search_page.py`

**Interfaces:**
- Consumes: `GET /api/search` and any-sid `POST /api/resume/` (Task 2).
- Produces: `showSessionModal(hit)` in app.js — Task 5 modifies the same modal; both set `modal.dataset.sessionId`.

- [ ] **Step 1: Write the failing E2E test**

Create `tests/e2e/test_search_page.py`:

```python
# ABOUTME: E2E tests for the search flow — type query, see hits, resume from a result.
# ABOUTME: Uses the shared e2e_server fixture (real server, fake resumer, fake recap runner).
from tests.conftest import add_session, add_message


def test_search_finds_session_and_resumes_it(page, e2e_server, ccrider_db):
    base_url, resumed, _, _ = e2e_server
    add_session(ccrider_db, "keep", "/Users/x/Code/bigproject", "2026-07-08 00:00:00", message_count=40)
    add_message(ccrider_db, "keep", "user", "refactor the parser", sequence=1)
    add_session(ccrider_db, "nas1", "/Users/x/Code/homelab", "2026-07-07 00:00:00", message_count=30)
    add_message(ccrider_db, "nas1", "user", "tune the synology nas raid", sequence=1)

    page.goto(base_url)
    page.fill("#searchBox", "synology")
    hit = page.locator(".search-hit")
    hit.wait_for()
    assert hit.count() == 1
    assert "homelab" in hit.inner_text()
    assert "synology" in hit.locator("strong").last.inner_text()  # «»-highlighted term

    hit.click()
    page.locator("#modalConfirm").click()
    page.wait_for_timeout(300)
    assert [r[0] for r in resumed] == ["nas1"]


def test_clearing_search_restores_journal(page, e2e_server, ccrider_db):
    base_url, _, _, _ = e2e_server
    add_session(ccrider_db, "keep", "/Users/x/Code/bigproject", "2026-07-08 00:00:00", message_count=40)
    add_message(ccrider_db, "keep", "user", "refactor the parser", sequence=1)

    page.goto(base_url)
    page.fill("#searchBox", "parser")
    page.locator(".search-hit").wait_for()
    page.fill("#searchBox", "")
    page.locator(".project:not(.search-hit)").wait_for()
    assert page.locator(".project:not(.search-hit)").count() == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `PLAYWRIGHT_BROWSERS_PATH=$(pwd)/.playwright-browsers .venv/bin/python -m pytest tests/e2e/test_search_page.py -q`
Expected: FAIL — `#searchBox` not found.

- [ ] **Step 3: Implement the UI**

`index.html` — replace the topbar block:

```html
  <div class="topbar">
    <a href="/" class="topbar-home"><h1>Reconvene<span class="cursor">▊</span></h1></a>
    <input id="searchBox" type="search" placeholder="Search sessions…" autocomplete="off">
    <a href="/settings.html">Settings</a>
  </div>
```

`app.js` — append at the end (before `loadJournal();`):

```js
// --- search -----------------------------------------------------------------
const searchBox = document.getElementById("searchBox");
let searchTimer = null;

searchBox.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(runSearch, 250);
});
searchBox.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    searchBox.value = "";
    runSearch();
  }
});

async function runSearch() {
  const q = searchBox.value.trim();
  if (!q) {
    loadJournal();
    return;
  }
  const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
  if (!res.ok) {
    const data = await res.json();
    showError(`Search failed: ${data.error}`);
    return;
  }
  const data = await res.json();
  renderResults(data.results, q);
}

function snippetNode(snippet) {
  // «…» regions become <strong>. Built via textContent — snippet text is untrusted.
  const span = document.createElement("span");
  const parts = snippet.split("«");
  span.appendChild(document.createTextNode(parts[0]));
  for (const part of parts.slice(1)) {
    const close = part.indexOf("»");
    const strong = document.createElement("strong");
    strong.textContent = close === -1 ? part : part.slice(0, close);
    span.appendChild(strong);
    if (close !== -1) span.appendChild(document.createTextNode(part.slice(close + 1)));
  }
  return span;
}

function renderResults(results, q) {
  const el = document.getElementById("journal");
  el.innerHTML = "";
  el.classList.remove("placeholder");
  if (results.length === 0) {
    el.classList.add("placeholder");
    el.textContent = `No sessions matching “${q}”.`;
    return;
  }
  for (const r of results) {
    const div = document.createElement("div");
    div.className = "project search-hit";
    const nameEl = document.createElement("strong");
    nameEl.textContent = r.project;
    const metaLine = document.createElement("div");
    metaLine.className = "meta-line";
    metaLine.textContent =
      `${r.relative} · ${r.message_count} msgs · ${r.hits} match${r.hits === 1 ? "" : "es"} · ${r.cwd}`;
    const snip = document.createElement("div");
    snip.className = "meta";
    snip.appendChild(snippetNode(r.snippet));
    div.append(nameEl, metaLine, snip);
    div.addEventListener("click", () => showSessionModal(r));
    el.appendChild(div);
  }
}

function showSessionModal(hit) {
  document.getElementById("modalProjectName").textContent = hit.project;
  const recapEl = document.getElementById("modalFullRecap");
  recapEl.innerHTML = "";
  recapEl.appendChild(snippetNode(hit.snippet));
  const modal = document.getElementById("confirmModal");
  modal.dataset.sessionId = hit.session_id;
  modal.dataset.projectName = hit.project;
  modal.classList.remove("hidden");
}
```

`style.css` — append:

```css
/* Search */
#searchBox {
  flex: 1;
  max-width: 340px;
  margin: 0 16px;
  padding: 6px 10px;
  font: inherit;
  color: inherit;
  background: var(--card-bg);
  border: 1px solid var(--border, #30363d);
  border-radius: 6px;
}
.search-hit .meta strong {
  font-weight: 700;
  text-decoration: underline;
}
```

- [ ] **Step 4: Run to verify pass**

Run: `PLAYWRIGHT_BROWSERS_PATH=$(pwd)/.playwright-browsers .venv/bin/python -m pytest tests/e2e/test_search_page.py -q` → pass.
Also run the whole e2e dir (topbar changed): `PLAYWRIGHT_BROWSERS_PATH=$(pwd)/.playwright-browsers .venv/bin/python -m pytest tests/e2e -q` → pass.

- [ ] **Step 5: Commit**

```bash
git add reconvene/web/static/index.html reconvene/web/static/app.js reconvene/web/static/style.css tests/e2e/test_search_page.py
git commit -m "feat: web search UI with highlighted snippets and resume-from-result"
```

---

### Task 4: `/api/sessions/<name>` endpoint

**Files:**
- Modify: `reconvene/web/server.py`
- Test: `tests/test_web_server.py`

**Interfaces:**
- Consumes: `build_journal`, `first_user_message` (already imported in server.py via `..recap`).
- Produces: `GET /api/sessions/<project-name>` → `{"sessions": [{session_id, updated_at, relative, message_count, first_msg}]}` newest-first. Task 5 consumes it.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_web_server.py`)

```python
def test_api_sessions_lists_project_sessions_newest_first(running_server, ccrider_db):
    base_url, _, _ = running_server
    add_session(ccrider_db, "r2", "/Users/x/Code/myproject", "2026-07-09 00:00:00", message_count=20)
    add_message(ccrider_db, "r2", "user", "second thread", sequence=1)
    with urllib.request.urlopen(f"{base_url}/api/sessions/myproject") as resp:
        data = json.loads(resp.read())
    assert [s["session_id"] for s in data["sessions"]] == ["r2", "r1"]
    assert data["sessions"][0]["first_msg"] == "second thread"
    assert data["sessions"][0]["message_count"] == 20


def test_api_sessions_unknown_project_404(running_server):
    base_url, _, _ = running_server
    with pytest.raises(HTTPError) as exc:
        urllib.request.urlopen(f"{base_url}/api/sessions/nope")
    assert exc.value.code == 404
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_web_server.py -q` — new tests FAIL (404 for both / wrong shape).

- [ ] **Step 3: Implement**

In `do_GET`, next to the `/api/recap/` block:

```python
            if path.startswith("/api/sessions/"):
                name = unquote(path[len("/api/sessions/"):])
                sessions = load_sessions(db_path)
                real, bots = build_journal(sessions, config)
                project = next((p for p in real + bots if p.name == name), None)
                if project is None:
                    self._send_json(404, {"error": f"no project named {name!r}"})
                    return
                self._send_json(200, {"sessions": [
                    {
                        "session_id": s.session_id,
                        "updated_at": s.updated_at,
                        "relative": relative_time(s.updated_at),
                        "message_count": s.message_count,
                        "first_msg": first_user_message(db_path, s.session_id),
                    }
                    for s in project.sessions
                ]})
                return
```

(`first_user_message` is already imported in server.py.)

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_web_server.py -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add reconvene/web/server.py tests/test_web_server.py
git commit -m "feat: /api/sessions/<name> lists a project's sessions"
```

---

### Task 5: Web modal session list

**Files:**
- Modify: `reconvene/web/static/index.html` (add `#modalSessions` container)
- Modify: `reconvene/web/static/app.js` (`showConfirmModal` fetches + renders the list; `showSessionModal` clears it)
- Modify: `reconvene/web/static/style.css` (`.session-row` styles)
- Test: `tests/e2e/test_journal_page.py` (append)

**Interfaces:**
- Consumes: `GET /api/sessions/<name>` (Task 4), `showSessionModal` (Task 3).
- Produces: modal rows with class `session-row` (selected row = `.session-row.selected`); Resume uses `modal.dataset.sessionId`.

- [ ] **Step 1: Write the failing E2E test** (append to `tests/e2e/test_journal_page.py`)

```python
def test_modal_lets_user_pick_an_older_session(page, e2e_server, ccrider_db):
    base_url, resumed, _, _ = e2e_server
    add_session(ccrider_db, "old", "/Users/x/Code/myproject", "2026-07-01 00:00:00", message_count=50)
    add_message(ccrider_db, "old", "user", "the nas deep dive", sequence=1)
    add_session(ccrider_db, "new", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "new", "user", "quick tweak", sequence=1)

    page.goto(base_url)
    page.locator(".project").first.click()
    rows = page.locator(".session-row")
    rows.nth(1).wait_for()
    assert rows.count() == 2
    assert "the nas deep dive" in rows.nth(1).inner_text()

    rows.nth(1).click()  # select the older session
    page.locator("#modalConfirm").click()
    page.wait_for_timeout(300)
    assert [r[0] for r in resumed] == ["old"]
```

- [ ] **Step 2: Run to verify failure**

Run: `PLAYWRIGHT_BROWSERS_PATH=$(pwd)/.playwright-browsers .venv/bin/python -m pytest tests/e2e/test_journal_page.py -q -k pick_an_older`
Expected: FAIL — `.session-row` never appears.

- [ ] **Step 3: Implement**

`index.html` — inside `.modal-content`, after `<p id="modalFullRecap"></p>`:

```html
      <div id="modalSessions"></div>
```

`app.js` — replace `showConfirmModal` with:

```js
function showConfirmModal(project) {
  document.getElementById("modalProjectName").textContent = project.name;
  document.getElementById("modalFullRecap").textContent =
    fullRecaps.get(project.name) || "Loading full summary…";
  const modal = document.getElementById("confirmModal");
  modal.dataset.sessionId = project.latest_session_id;
  modal.dataset.projectName = project.name;
  const list = document.getElementById("modalSessions");
  list.innerHTML = "";
  fetch(`/api/sessions/${encodeURIComponent(project.name)}`)
    .then((r) => r.json())
    .then((data) => {
      if (!data.sessions || data.sessions.length < 2) return; // one session: nothing to pick
      for (const s of data.sessions) {
        const row = document.createElement("div");
        row.className = "session-row";
        if (s.session_id === modal.dataset.sessionId) row.classList.add("selected");
        row.textContent = `${s.relative} · ${s.message_count} msgs · ${s.first_msg}`;
        row.addEventListener("click", () => {
          modal.dataset.sessionId = s.session_id;
          list.querySelectorAll(".session-row.selected")
            .forEach((n) => n.classList.remove("selected"));
          row.classList.add("selected");
        });
        list.appendChild(row);
      }
    })
    .catch((err) => console.error(`Failed to fetch sessions for ${project.name}:`, err));
  modal.classList.remove("hidden");
}
```

And in `showSessionModal` (Task 3), add before `modal.classList.remove("hidden");`:

```js
  document.getElementById("modalSessions").innerHTML = "";
```

`style.css` — append:

```css
/* Session picker inside the resume modal */
.session-row {
  padding: 6px 8px;
  margin: 4px 0;
  border: 1px solid transparent;
  border-radius: 6px;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.session-row:hover { background: var(--card-bg); }
.session-row.selected {
  border-color: var(--dot-active);
  background: var(--card-bg);
}
```

- [ ] **Step 4: Run to verify pass**

Run: `PLAYWRIGHT_BROWSERS_PATH=$(pwd)/.playwright-browsers .venv/bin/python -m pytest tests/e2e -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add reconvene/web/static/index.html reconvene/web/static/app.js reconvene/web/static/style.css tests/e2e/test_journal_page.py
git commit -m "feat: modal session list — pick any session to resume"
```

---

### Task 6: `_preview` session mode + `_search` module (TUI plumbing)

**Files:**
- Modify: `reconvene/_preview.py` (optional `--session` mode)
- Create: `reconvene/_search.py`
- Test: `tests/test_preview.py` (append), `tests/test_search.py` (append)

**Interfaces:**
- Consumes: `search_sessions`, `SNIPPET_OPEN/SNIPPET_CLOSE` (Task 1); `load_sessions`, `first_user_message`, `canonical_name`, `relative_time`, `abbreviate_home`.
- Produces: `python -m reconvene._preview <sid> <db> <cache> <config> --session` prints a per-session detail pane; `python -m reconvene._search <query> <db>` prints `sid\t<project> · <relative> · <N>✓ · <snippet>` lines (markers stripped, tabs/newlines flattened). `reconvene._search.render_hit(hit) -> str`. Tasks 7–8 embed these in fzf commands.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_preview.py`:

```python
def test_preview_session_mode_shows_first_message_and_summary(tmp_path, ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00",
                message_count=12, summary="ccrider's own summary")
    add_message(ccrider_db, "s1", "user", "tune the nas raid", sequence=1)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = _preview.main(["s1", str(ccrider_db), str(tmp_path / "r.db"),
                            _none_config(tmp_path), "--session"])
    out = buf.getvalue()
    assert rc == 0
    assert "myproject" in out
    assert "12 messages" in out
    assert "tune the nas raid" in out
    assert "ccrider's own summary" in out


def test_preview_session_mode_unknown_sid(tmp_path, ccrider_db):
    buf = io.StringIO()
    with redirect_stdout(buf):
        _preview.main(["nope", str(ccrider_db), str(tmp_path / "r.db"),
                       _none_config(tmp_path), "--session"])
    assert "(session not found)" in buf.getvalue()
```

Append to `tests/test_search.py`:

```python
import io
from contextlib import redirect_stdout

from reconvene import _search


def test_search_module_prints_tab_delimited_lines(ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/homelab", "2026-07-08 00:00:00", message_count=9)
    add_message(ccrider_db, "s1", "user", "pihole dns setup", sequence=1)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = _search.main(["pihole", str(ccrider_db)])
    assert rc == 0
    line = buf.getvalue().strip()
    sid, display = line.split("\t", 1)
    assert sid == "s1"
    assert "homelab" in display and "1✓" in display
    assert "«" not in display and "»" not in display  # markers stripped for terminal


def test_search_module_empty_query_prints_nothing(ccrider_db):
    buf = io.StringIO()
    with redirect_stdout(buf):
        _search.main(["", str(ccrider_db)])
    assert buf.getvalue() == ""
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_preview.py tests/test_search.py -q`
Expected: new tests FAIL (`--session` treated as unknown / no `_search` module).

- [ ] **Step 3: Implement**

`reconvene/_preview.py` — add these imports (keep existing ones; some of these may already be present):

```python
from .classify import canonical_name
from .db import load_sessions
from .journal import abbreviate_home, relative_time
from .recap import first_user_message
```

Add:

```python
def _print_session_detail(session, db_path):
    print(canonical_name(session.project_path))
    print(f"session {session.session_id[:8]} · {relative_time(session.updated_at)}"
          f" · {session.message_count} messages")
    print(f"path  {abbreviate_home(session.project_path)}")
    print("─" * 46)
    print()
    print(first_user_message(db_path, session.session_id, limit=400) or "(no messages)")
    if session.summary:
        print()
        print(session.summary)
```

Rework `main` to branch on the flag (full replacement):

```python
def main(argv, *, recaps_fn=ensure_recaps) -> int:
    session_mode = "--session" in argv
    argv = [a for a in argv if a != "--session"]
    session_id, db_path, cache_path, config_path = argv[0], argv[1], argv[2], argv[3]
    try:
        config = load_config(config_path)
        if session_mode:
            session = next((s for s in load_sessions(db_path) if s.session_id == session_id), None)
            if session is None:
                print("(session not found)")
                return 0
            _print_session_detail(session, db_path)
            return 0
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
        _print_recap(project, db_path, cache_path, config, recaps_fn)
    except Exception as e:
        print(f"⚠ recap unavailable: {e}")
    return 0
```

Create `reconvene/_search.py`:

```python
# ABOUTME: fzf change:reload target for TUI search — prints one tab-delimited line per FTS hit.
# ABOUTME: Line format: sid<TAB>project · relative · N✓ · snippet (markers stripped, whitespace flat).
import sys

from .classify import canonical_name
from .journal import relative_time
from .search import SNIPPET_CLOSE, SNIPPET_OPEN, search_sessions


def render_hit(hit) -> str:
    snippet = (hit.snippet
               .replace(SNIPPET_OPEN, "").replace(SNIPPET_CLOSE, "")
               .replace("\t", " ").replace("\n", " "))
    return (f"{hit.session_id}\t{canonical_name(hit.project_path)}"
            f" · {relative_time(hit.updated_at)} · {hit.hits}✓ · {snippet}")


def main(argv) -> int:
    query, db_path = argv[0], argv[1]
    try:
        hits = search_sessions(db_path, query)
    except RuntimeError as e:
        print(f"⚠ search unavailable: {e}")
        return 0
    for h in hits:
        print(render_hit(h))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_preview.py tests/test_search.py -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add reconvene/_preview.py reconvene/_search.py tests/test_preview.py tests/test_search.py
git commit -m "feat: per-session preview mode and _search reload module for the TUI"
```

---

### Task 7: TUI picker protocol + session drill-in (`ctrl-s`)

**Files:**
- Modify: `reconvene/tui.py`
- Test: `tests/test_tui.py`

**Interfaces:**
- Consumes: `_preview_command` gains `session=False` kwarg (appends ` --session`); `exec_resume`.
- Produces: **picker protocol change** — every picker (injected or real) now returns `(key, chosen_line_or_None)`; `render_session_line(session, db_path) -> str`; `run_tui` handles key `"ctrl-s"` by opening a session-level picker (`session_picker` injectable kwarg). Task 8 adds `"ctrl-f"` on top of this protocol.

- [ ] **Step 1: Update existing tests to the tuple protocol and add drill-in tests**

In `tests/test_tui.py`, every injected `picker=lambda lines: X` becomes `picker=lambda lines: ("", X)`. Concretely:
- `test_run_tui_resumes_selected`: `picker=lambda lines: ("", lines[0])`
- `test_run_tui_no_pick_returns_0`: `picker=lambda lines: ("", None)`
- `test_run_tui_separator_pick_does_not_resume`: `picker=lambda lines: ("", next(l for l in lines if "automated" in l.lower()))`
- `test_run_tui_empty_returns_1`: `picker=lambda lines: ("", lines[0]) if lines else ("", None)`
- `test_run_tui_bots_hidden_without_flag`: `picker=lambda lines: seen.setdefault("lines", lines) and ("", None)`
- `test_run_tui_only_bots_without_flag_returns_1`: `picker=lambda lines: opened.append(lines) or ("", None)`
- `test_run_tui_does_not_generate_recaps_up_front`: `picker=lambda lines: seen.setdefault("lines", lines) and ("", None)`

Append new tests:

```python
def test_render_session_line_format(tmp_path, ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=7)
    add_message(ccrider_db, "s1", "user", "fix the flaky test", sequence=1)
    from reconvene.db import load_sessions
    (session,) = load_sessions(str(ccrider_db))
    line = tui.render_session_line(session, str(ccrider_db))
    sid, display = line.split("\t", 1)
    assert sid == "s1"
    assert "7 msgs" in display and "fix the flaky test" in display


def test_run_tui_ctrl_s_drills_into_sessions_and_resumes_picked(tmp_path, ccrider_db):
    add_session(ccrider_db, "old", "/Users/x/Code/myproject", "2026-07-01 00:00:00", message_count=50)
    add_message(ccrider_db, "old", "user", "the nas deep dive", sequence=1)
    add_session(ccrider_db, "new", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "new", "user", "quick tweak", sequence=1)
    resumed = []
    rc = tui.run_tui(
        Config(recap_auth_mode="none"), str(ccrider_db), str(tmp_path / "r.db"), str(tmp_path / "c.json"),
        picker=lambda lines: ("ctrl-s", lines[0]),          # drill into the (only) project
        session_picker=lambda lines: ("", next(l for l in lines if l.startswith("old\t"))),
        resumer=lambda sid, cwd, updated_at, config: resumed.append((sid, cwd)),
    )
    assert rc == 0
    assert resumed == [("old", "/Users/x/Code/myproject")]


def test_run_tui_ctrl_s_esc_returns_to_projects(tmp_path, ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "hi", sequence=1)
    resumed = []
    project_picks = iter([("ctrl-s", None), ("", None)])   # ctrl-s with no line, then quit
    rc = tui.run_tui(
        Config(recap_auth_mode="none"), str(ccrider_db), str(tmp_path / "r.db"), str(tmp_path / "c.json"),
        picker=lambda lines: next(project_picks),
        session_picker=lambda lines: ("", None),           # esc inside the session view
        resumer=lambda *a: resumed.append(a),
    )
    assert rc == 0
    assert resumed == []
```

(Note the second test: `("ctrl-s", None)` — ctrl-s pressed with no highlightable line — must NOT crash; it re-shows the project picker.)

Also update `test_preview_command_references_the_preview_module_and_paths` — add:

```python
    session_cmd = tui._preview_command("/db/x.db", "/c/r.db", "/cfg/c.json", session=True)
    assert session_cmd.endswith(" --session")
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_tui.py -q`
Expected: FAIL — tuple protocol not implemented, `render_session_line` missing, `session_picker` unexpected kwarg.

- [ ] **Step 3: Implement in `reconvene/tui.py`**

Add import: `from .recap import first_user_message`.

`_preview_command` gains the mode kwarg:

```python
def _preview_command(db_path, cache_path, config_path, session=False) -> str:
    # ... (existing comment unchanged) ...
    pkg_root = str(Path(__file__).resolve().parent.parent)
    cmd = (
        f"PYTHONPATH={shlex.quote(pkg_root)} {shlex.quote(sys.executable)} "
        f"-m reconvene._preview {{1}} "
        f"{shlex.quote(db_path)} {shlex.quote(cache_path)} {shlex.quote(config_path)}"
    )
    return cmd + " --session" if session else cmd
```

New renderer:

```python
def render_session_line(session, db_path) -> str:
    first = first_user_message(db_path, session.session_id, limit=70)
    return (f"{session.session_id}\t{relative_time(session.updated_at)}"
            f" · {session.message_count} msgs · {first}")
```

`_make_fzf_picker` — tuple protocol + `--expect`:

```python
def _make_fzf_picker(preview_cmd, expect=()):
    # Returns (key, chosen_line). key is "" for a plain enter; with --expect, fzf prints the
    # pressed key on the first output line and the highlighted line on the second. esc/abort
    # yields ("", None).
    def picker(lines):
        cmd = ["fzf", "--no-sort", "--layout=reverse", "--border=rounded", "--info=inline",
               "--delimiter", "\t", "--with-nth", "2..",
               "--preview", preview_cmd,
               "--preview-window", "right:65%:wrap"]
        if expect:
            cmd += ["--expect", ",".join(expect)]
        proc = subprocess.run(cmd, input="\n".join(lines), capture_output=True, text=True)
        out = proc.stdout.splitlines()
        if not expect:
            return ("", out[0] if out and out[0] else None)
        if not out:
            return ("", None)
        key = out[0].strip()
        chosen = out[1] if len(out) > 1 and out[1] else None
        return (key, chosen)
    return picker
```

`run_tui` — view loop (full replacement of the body after the empty-view check; signature gains `session_picker=None`):

```python
def run_tui(config, db_path, cache_path, config_path, show_bots=False, *,
            picker=None, session_picker=None, resumer=exec_resume) -> int:
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
    project_picker = picker or _make_fzf_picker(
        _preview_command(db_path, cache_path, config_path), expect=("ctrl-s",))
    active_session_picker = session_picker or _make_fzf_picker(
        _preview_command(db_path, cache_path, config_path, session=True))

    while True:
        key, chosen = project_picker(lines)
        if not chosen and key != "ctrl-s":
            return 0
        project = sid_to_project.get(chosen.split("\t", 1)[0]) if chosen else None
        if project is None:
            if key == "ctrl-s":
                continue  # ctrl-s on a separator/empty line: just re-show the list
            return 0      # separator picked with enter
        if key == "ctrl-s":
            session_lines = [render_session_line(s, db_path) for s in project.sessions]
            _, s_chosen = active_session_picker(session_lines)
            if not s_chosen:
                continue  # esc: back to the project list
            sid = s_chosen.split("\t", 1)[0]
            session = next((s for s in project.sessions if s.session_id == sid), None)
            if session is None:
                continue
            resumer(session.session_id, session.project_path, session.updated_at, config)
            return 0
        resumer(project.latest.session_id, project.latest.project_path,
                project.latest.updated_at, config)
        return 0
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_tui.py -q` → all pass. Then full non-e2e suite.

- [ ] **Step 5: Commit**

```bash
git add reconvene/tui.py tests/test_tui.py
git commit -m "feat: TUI session drill-in via ctrl-s; picker protocol carries expect keys"
```

---

### Task 8: TUI search mode (`ctrl-f`) + CLI `-s/--search`

**Files:**
- Modify: `reconvene/tui.py` (search picker, `ctrl-f`, `initial_search`)
- Modify: `reconvene/cli.py` (`-s/--search` flag)
- Test: `tests/test_tui.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `reconvene._search` module (Task 6), tuple picker protocol (Task 7), `search_sessions`.
- Produces: `run_tui(..., search_picker=None, initial_search=None)`; `_search_reload_command(db_path) -> str`; CLI `-s [QUERY]` launches the TUI directly in search mode.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_tui.py`:

```python
def test_run_tui_ctrl_f_search_resumes_hit(tmp_path, ccrider_db):
    add_session(ccrider_db, "hit", "/Users/x/Code/homelab", "2026-07-07 00:00:00", message_count=30)
    add_message(ccrider_db, "hit", "user", "tune the synology nas", sequence=1)
    add_session(ccrider_db, "other", "/Users/x/Code/webapp", "2026-07-08 00:00:00", message_count=30)
    add_message(ccrider_db, "other", "user", "css fixes", sequence=1)
    resumed = []
    rc = tui.run_tui(
        Config(recap_auth_mode="none"), str(ccrider_db), str(tmp_path / "r.db"), str(tmp_path / "c.json"),
        picker=lambda lines: ("ctrl-f", None),
        search_picker=lambda query: "hit\thomelab · 12d ago · 1✓ · …",
        resumer=lambda sid, cwd, updated_at, config: resumed.append((sid, cwd)),
    )
    assert rc == 0
    assert resumed == [("hit", "/Users/x/Code/homelab")]


def test_run_tui_search_esc_returns_to_projects(tmp_path, ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "hi", sequence=1)
    picks = iter([("ctrl-f", None), ("", None)])
    resumed = []
    rc = tui.run_tui(
        Config(recap_auth_mode="none"), str(ccrider_db), str(tmp_path / "r.db"), str(tmp_path / "c.json"),
        picker=lambda lines: next(picks),
        search_picker=lambda query: None,   # esc in search view
        resumer=lambda *a: resumed.append(a),
    )
    assert rc == 0
    assert resumed == []


def test_run_tui_initial_search_skips_project_view(tmp_path, ccrider_db):
    add_session(ccrider_db, "hit", "/Users/x/Code/homelab", "2026-07-07 00:00:00", message_count=30)
    add_message(ccrider_db, "hit", "user", "pihole", sequence=1)
    resumed = []
    queries = []
    rc = tui.run_tui(
        Config(recap_auth_mode="none"), str(ccrider_db), str(tmp_path / "r.db"), str(tmp_path / "c.json"),
        picker=lambda lines: (_ for _ in ()).throw(AssertionError("project picker must not run")),
        search_picker=lambda query: queries.append(query) or "hit\thomelab · 12d ago · 1✓ · …",
        resumer=lambda sid, cwd, updated_at, config: resumed.append(sid),
        initial_search="pihole",
    )
    assert rc == 0
    assert queries == ["pihole"]
    assert resumed == ["hit"]


def test_search_reload_command_shape():
    cmd = tui._search_reload_command("/db/sessions.db")
    assert "-m reconvene._search" in cmd
    assert "{q}" in cmd
    assert "/db/sessions.db" in cmd
    assert "PYTHONPATH=" in cmd
```

Append to `tests/test_cli.py` (match the file's existing fake-launcher style — it passes `launch_tui=` fakes; follow the signature used by the existing `test_main_tui_passes_bots_flag` test and extend it with the new kwarg):

```python
def test_main_search_flag_launches_tui_in_search_mode(tmp_path):
    calls = {}
    def fake_tui(config, db, cache, config_path, bots, initial_search=None):
        calls["initial_search"] = initial_search
        return 0
    rc = main(["--no-sync", "--db", str(tmp_path / "x.db"), "--cache", str(tmp_path / "r.db"),
               "--config", str(tmp_path / "c.json"), "-s", "pihole"],
              stdin_isatty=True, input_fn=lambda _: "2", launch_tui=fake_tui)
    assert rc == 0
    assert calls["initial_search"] == "pihole"
```

(If the existing fake `launch_tui` signatures in `test_cli.py` differ, update them all to accept `initial_search=None` — the dispatch adds a kwarg.)

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_tui.py tests/test_cli.py -q` — new tests FAIL.

- [ ] **Step 3: Implement**

`reconvene/tui.py`:

```python
def _search_reload_command(db_path) -> str:
    # fzf substitutes {q} with the current query and re-runs this on every keystroke
    # (change:reload). FTS answers in ~10ms, so live search is cheap.
    pkg_root = str(Path(__file__).resolve().parent.parent)
    return (
        f"PYTHONPATH={shlex.quote(pkg_root)} {shlex.quote(sys.executable)} "
        f"-m reconvene._search {{q}} {shlex.quote(db_path)}"
    )


def _make_fzf_search_picker(db_path, cache_path, config_path):
    # --disabled turns off fzf's own filtering: the line set IS the result set, reloaded from
    # FTS on each keystroke. Returns the chosen line or None (esc).
    preview_cmd = _preview_command(db_path, cache_path, config_path, session=True)
    reload_cmd = _search_reload_command(db_path)

    def search_picker(query):
        initial = subprocess.run(
            [sys.executable, "-m", "reconvene._search", query, db_path],
            capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parent.parent)},
        ).stdout
        proc = subprocess.run(
            ["fzf", "--disabled", "--query", query, "--no-sort", "--layout=reverse",
             "--border=rounded", "--info=inline", "--prompt", "search> ",
             "--delimiter", "\t", "--with-nth", "2..",
             "--bind", f"change:reload:{reload_cmd}",
             "--preview", preview_cmd,
             "--preview-window", "right:65%:wrap"],
            input=initial, capture_output=True, text=True,
        )
        return proc.stdout.strip() or None
    return search_picker
```

Add `import os` to tui.py's imports.

In `run_tui`: signature becomes

```python
def run_tui(config, db_path, cache_path, config_path, show_bots=False, *,
            picker=None, session_picker=None, search_picker=None,
            resumer=exec_resume, initial_search=None) -> int:
```

Build `all_by_sid = {s.session_id: s for s in sessions}` after `load_sessions`, and `active_search_picker = search_picker or _make_fzf_search_picker(db_path, cache_path, config_path)` next to the other pickers. Add a search helper inside `run_tui`:

```python
    def _run_search(query) -> int | None:
        # Returns 0 if a session was resumed, None to fall back to the project view.
        s_chosen = active_search_picker(query)
        if not s_chosen:
            return None
        sid = s_chosen.split("\t", 1)[0]
        session = all_by_sid.get(sid)
        if session is None:
            return None
        resumer(session.session_id, session.project_path, session.updated_at, config)
        return 0
```

Before the `while True` loop:

```python
    if initial_search is not None:
        result = _run_search(initial_search)
        if result is not None:
            return result
        # esc from an initial search falls through to the project view
```

Project picker gains the key: `expect=("ctrl-s", "ctrl-f")`. Inside the loop, handle it first:

```python
        if key == "ctrl-f":
            result = _run_search("")
            if result is not None:
                return result
            continue
```

(Place this immediately after `key, chosen = project_picker(lines)`, before the `if not chosen` check — ctrl-f is valid regardless of the highlighted line.)

`reconvene/cli.py`:

```python
    ap.add_argument("-s", "--search", nargs="?", const="", default=None, metavar="QUERY",
                    help="open the TUI directly in search mode (optional initial query)")
```

Dispatch: search implies the TUI and skips the chooser —

```python
    interactive = sys.stdin.isatty() if stdin_isatty is None else stdin_isatty
    if args.search is not None:
        mode = "tui"
    else:
        mode = _choose_frontend(input_fn) if interactive else "web"
    if mode is None:
        return 0  # user cancelled the chooser
```

and the TUI call becomes:

```python
    if mode == "tui":
        return (launch_tui or run_tui)(config, args.db, args.cache, args.config, args.bots,
                                       initial_search=args.search)
```

(`run_tui`'s 5th positional is `show_bots`; `initial_search=None` when `-s` wasn't given.)

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_tui.py tests/test_cli.py -q` → all pass. Then the full non-e2e suite.

- [ ] **Step 5: Commit**

```bash
git add reconvene/tui.py reconvene/cli.py tests/test_tui.py tests/test_cli.py
git commit -m "feat: live FTS search mode in the TUI (ctrl-f, reconvene -s)"
```

---

### Task 9: Root detection, TopicCache, and loose-session journal grouping

**Files:**
- Create: `reconvene/cluster.py` (detection + cache only; organize comes in Task 10)
- Modify: `reconvene/journal.py` (`Project.kind`, loose grouping in `_group_projects`, `build_journal(..., topic_lookup=None)`)
- Modify: `reconvene/web/server.py` (pass `topic_lookup`; expose `kind` in summaries)
- Modify: `reconvene/tui.py` (pass `topic_lookup`; `render_line` kind markers)
- Modify: `reconvene/_preview.py` (`_find_project` passes `topic_lookup`)
- Test: `tests/test_cluster.py` (new), `tests/test_journal.py`, `tests/test_web_server.py`, `tests/test_tui.py` (append)

**Interfaces:**
- Consumes: `WORKTREE_MARKERS`, `NOISE_MESSAGE_FLOOR` (constants), `abbreviate_home`.
- Produces: `detect_roots(paths: set[str]) -> set[str]` (rstripped paths); `TopicCache(path)` with `.get_all() -> dict[str, str]`, `.assign(session_id, topic)` (INSERT OR IGNORE), `.topics() -> set[str]`, `.close()`; `FALLBACK_SUFFIX = " (loose sessions)"`; `Project` gains `kind: str = "project"` (`"project" | "topic" | "loose"`); `build_journal(sessions, config, topic_lookup=None)`; `load_topic_lookup(cache_path) -> dict[str, str]` helper in cluster.py. Task 10 builds organize on these.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cluster.py`:

```python
# ABOUTME: Tests for root detection and the sticky TopicCache.
# ABOUTME: Roots = paths prefixing >=3 other session paths (worktree children excluded).
from reconvene.cluster import TopicCache, detect_roots, load_topic_lookup


def test_detect_roots_needs_three_distinct_children():
    paths = {"/u/Code", "/u/Code/a", "/u/Code/b", "/u/Code/c"}
    assert detect_roots(paths) == {"/u/Code"}


def test_detect_roots_two_children_is_not_a_root():
    assert detect_roots({"/u/Code", "/u/Code/a", "/u/Code/b"}) == set()


def test_detect_roots_ignores_worktree_children():
    paths = {"/u/Code/foo",
             "/u/Code/foo/.claude-worktrees/a",
             "/u/Code/foo/.claude-worktrees/b",
             "/u/Code/foo/.claude-worktrees/c"}
    assert detect_roots(paths) == set()


def test_detect_roots_candidate_must_be_a_session_path():
    # /u/Code prefixes three paths but is not itself a session's project_path.
    assert detect_roots({"/u/Code/a", "/u/Code/b", "/u/Code/c"}) == set()


def test_detect_roots_prefix_is_segment_aligned():
    # /u/Code must not claim /u/Codebase as a child.
    paths = {"/u/Code", "/u/Codebase1", "/u/Codebase2", "/u/Codebase3"}
    assert detect_roots(paths) == set()


def test_topic_cache_assign_is_sticky(tmp_path):
    cache = TopicCache(str(tmp_path / "r.db"))
    cache.assign("s1", "NAS & Pi-Hole")
    cache.assign("s1", "Something Else")     # must NOT overwrite
    assert cache.get_all() == {"s1": "NAS & Pi-Hole"}
    assert cache.topics() == {"NAS & Pi-Hole"}
    cache.close()


def test_load_topic_lookup_roundtrip(tmp_path):
    cache = TopicCache(str(tmp_path / "r.db"))
    cache.assign("s1", "Desktop Cleanup")
    cache.close()
    assert load_topic_lookup(str(tmp_path / "r.db")) == {"s1": "Desktop Cleanup"}
```

Append to `tests/test_journal.py` (imports at top already include `Config`, `Session`; add `add_session`-style raw Sessions as the file does — it constructs `Session` tuples directly in places; follow its local pattern using `Session(sid, path, updated, updated, count, None, None)`):

```python
def _sess(sid, path, updated, count=10):
    return Session(sid, path, updated, updated, count, None, None)


def test_loose_sessions_group_under_fallback_without_topics():
    sessions = [
        _sess("p1", "/Users/x/Code/alpha", "2026-07-01 00:00:00"),
        _sess("p2", "/Users/x/Code/beta", "2026-07-02 00:00:00"),
        _sess("p3", "/Users/x/Code/gamma", "2026-07-03 00:00:00"),
        _sess("l1", "/Users/x/Code", "2026-07-08 00:00:00", count=20),
        _sess("l2", "/Users/x/Code", "2026-07-07 00:00:00", count=30),
    ]
    real, bots = build_journal(sessions, Config())
    loose = [p for p in real if p.kind == "loose"]
    assert len(loose) == 1
    assert loose[0].name.endswith(" (loose sessions)")
    assert {s.session_id for s in loose[0].sessions} == {"l1", "l2"}
    assert all(p.kind == "project" for p in real if p is not loose[0])


def test_loose_sessions_with_topics_become_topic_groups():
    sessions = [
        _sess("p1", "/Users/x/Code/alpha", "2026-07-01 00:00:00"),
        _sess("p2", "/Users/x/Code/beta", "2026-07-02 00:00:00"),
        _sess("p3", "/Users/x/Code/gamma", "2026-07-03 00:00:00"),
        _sess("l1", "/Users/x/Code", "2026-07-08 00:00:00", count=20),
        _sess("l2", "/Users/x/Code", "2026-07-07 00:00:00", count=30),
    ]
    real, _ = build_journal(sessions, Config(), topic_lookup={"l1": "NAS & Pi-Hole"})
    topic = next(p for p in real if p.kind == "topic")
    assert topic.name == "NAS & Pi-Hole"
    assert [s.session_id for s in topic.sessions] == ["l1"]
    assert any(p.kind == "loose" and p.sessions[0].session_id == "l2" for p in real)


def test_loose_noise_sessions_still_dropped():
    sessions = [
        _sess("p1", "/Users/x/Code/alpha", "2026-07-01 00:00:00"),
        _sess("p2", "/Users/x/Code/beta", "2026-07-02 00:00:00"),
        _sess("p3", "/Users/x/Code/gamma", "2026-07-03 00:00:00"),
        _sess("noise", "/Users/x/Code", "2026-07-08 00:00:00", count=2),
    ]
    real, _ = build_journal(sessions, Config())
    assert not any(p.kind in ("loose", "topic") for p in real)


def test_hidden_names_hides_topic_groups():
    sessions = [
        _sess("p1", "/Users/x/Code/alpha", "2026-07-01 00:00:00"),
        _sess("p2", "/Users/x/Code/beta", "2026-07-02 00:00:00"),
        _sess("p3", "/Users/x/Code/gamma", "2026-07-03 00:00:00"),
        _sess("l1", "/Users/x/Code", "2026-07-08 00:00:00", count=20),
    ]
    config = Config(hidden_names={"nas & pi-hole"})
    real, _ = build_journal(sessions, config, topic_lookup={"l1": "NAS & Pi-Hole"})
    assert not any(p.kind == "topic" for p in real)
```

Append to `tests/test_web_server.py`:

```python
def test_api_journal_reports_kind_and_topic_groups(running_server, ccrider_db, tmp_path):
    base_url, _, _ = running_server
    for i, sub in enumerate(("alpha", "beta", "gamma")):
        add_session(ccrider_db, f"p{i}", f"/Users/x/Code/{sub}", "2026-07-01 00:00:00", message_count=10)
        add_message(ccrider_db, f"p{i}", "user", "work", sequence=1)
    add_session(ccrider_db, "l1", "/Users/x/Code", "2026-07-09 00:00:00", message_count=20)
    add_message(ccrider_db, "l1", "user", "loose thread", sequence=1)
    with urllib.request.urlopen(f"{base_url}/api/journal") as resp:
        data = json.loads(resp.read())
    kinds = {p["name"]: p["kind"] for p in data["real"]}
    assert kinds["myproject"] == "project"
    assert any(k == "loose" for k in kinds.values())
```

Append to `tests/test_tui.py`:

```python
def test_render_line_marks_topic_and_loose_kinds():
    p = _p("NAS & Pi-Hole", "real", "s1", "/Users/x/Code", "2026-07-08 10:00:00")
    p.kind = "topic"
    assert tui.render_line(p).endswith("· topic")
    p2 = _p("~/Code (loose sessions)", "real", "s2", "/Users/x/Code", "2026-07-08 10:00:00")
    p2.kind = "loose"
    assert tui.render_line(p2).endswith("· unorganized")
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_cluster.py tests/test_journal.py tests/test_web_server.py tests/test_tui.py -q` — new tests FAIL.

- [ ] **Step 3: Implement**

Create `reconvene/cluster.py` (detection + cache; organize lands in Task 10):

```python
# ABOUTME: Root-launch detection and sticky topic assignments for "loose" sessions.
# ABOUTME: A root = a session path that path-prefixes >=3 other session paths (worktrees excluded).
import sqlite3
from pathlib import Path

from .constants import WORKTREE_MARKERS

FALLBACK_SUFFIX = " (loose sessions)"


def detect_roots(paths) -> set[str]:
    norm = {p.rstrip("/") for p in paths if p and p.rstrip("/")}
    roots = set()
    for cand in norm:
        prefix = cand + "/"
        children = {
            p for p in norm
            if p != cand and p.startswith(prefix)
            and not any(m in p[len(cand):] for m in WORKTREE_MARKERS)
        }
        if len(children) >= 3:
            roots.add(cand)
    return roots


class TopicCache:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS topic_assignments "
            "(session_id TEXT PRIMARY KEY, topic TEXT NOT NULL)"
        )
        self.conn.commit()

    def get_all(self) -> dict[str, str]:
        return dict(self.conn.execute("SELECT session_id, topic FROM topic_assignments"))

    def assign(self, session_id, topic):
        # OR IGNORE = stickiness: an existing assignment is never overwritten.
        self.conn.execute(
            "INSERT OR IGNORE INTO topic_assignments(session_id, topic) VALUES (?, ?)",
            (session_id, topic),
        )
        self.conn.commit()

    def topics(self) -> set[str]:
        return {t for (t,) in self.conn.execute("SELECT DISTINCT topic FROM topic_assignments")}

    def close(self):
        self.conn.close()


def load_topic_lookup(cache_path) -> dict[str, str]:
    cache = TopicCache(cache_path)
    try:
        return cache.get_all()
    finally:
        cache.close()
```

`reconvene/journal.py` — `Project` gains `kind` (default `"project"`, so every existing constructor call stays valid):

```python
@dataclass
class Project:
    name: str
    category: str
    sessions: list[Session]
    kind: str = "project"  # "project" | "topic" (LLM-assigned group) | "loose" (unorganized root launches)
```

Imports: `from .cluster import FALLBACK_SUFFIX, detect_roots` and `from .constants import DROP_SUBSTRINGS, NOISE_MESSAGE_FLOOR` — wait: classify already applies those; for loose sessions apply them here (see below). Add to the existing import block:

```python
from .cluster import FALLBACK_SUFFIX, detect_roots
from .constants import NOISE_MESSAGE_FLOOR
```

`_group_projects` full replacement:

```python
def _group_projects(sessions, config, topic_lookup=None):
    # Group sessions into Projects keyed by (category, canonical name). Noise-dropped sessions are
    # excluded; user-hidden ("hidden") ones are kept so the settings view can surface them.
    # Sessions launched from a root directory (one that path-prefixes >=3 real project paths, e.g.
    # bare ~/Code) don't belong to a nameable project: they group by cached topic assignment, or
    # fall back to one visibly-generic "<root> (loose sessions)" group per root.
    topic_lookup = topic_lookup or {}
    roots = detect_roots({s.project_path for s in sessions})
    hidden_lower = {n.lower() for n in config.hidden_names}
    groups: dict[tuple, list[Session]] = {}
    for s in sessions:
        if s.project_path.rstrip("/") in roots:
            if s.message_count <= NOISE_MESSAGE_FLOOR:
                continue
            topic = topic_lookup.get(s.session_id)
            if topic:
                name, kind = topic, "topic"
            else:
                name, kind = abbreviate_home(s.project_path.rstrip("/")) + FALLBACK_SUFFIX, "loose"
            cat = "hidden" if name.lower() in hidden_lower else "real"
            groups.setdefault((cat, name, kind), []).append(s)
            continue
        cat = classify_category(s.project_path, config, s.message_count)
        if cat == "drop":
            continue
        groups.setdefault((cat, canonical_name(s.project_path), "project"), []).append(s)
    projects = []
    for (cat, name, kind), sess in groups.items():
        sess.sort(key=lambda s: s.updated_at, reverse=True)
        projects.append(Project(name=name, category=cat, sessions=sess, kind=kind))
    return projects


def build_journal(sessions, config, topic_lookup=None):
    projects = _group_projects(sessions, config, topic_lookup)
    return _by_recency(projects, "real"), _by_recency(projects, "bot")


def build_settings_projects(sessions, config, topic_lookup=None):
    # Real + bot + user-hidden projects, for the settings table -- so a hidden project stays visible
    # there (as a "Hidden" row) and can be toggled back. Noise-dropped projects remain excluded.
    projects = _group_projects(sessions, config, topic_lookup)
    return _by_recency(projects, "real") + _by_recency(projects, "bot") + _by_recency(projects, "hidden")
```

`reconvene/web/server.py` — thread the lookup through:

- Import: `from ..cluster import load_topic_lookup`.
- In `make_handler`, add a helper used by every journal-building route:

```python
    def _journal(sessions):
        return build_journal(sessions, config, topic_lookup=load_topic_lookup(cache_path))
```

  (Define it inside `make_handler`, above `class Handler`.) Replace all three `build_journal(sessions, config)` call sites (`/api/journal`, `/api/recap/`, `/api/sessions/`) with `_journal(sessions)`. `/api/settings` GET: `build_settings_projects(sessions, config, topic_lookup=load_topic_lookup(cache_path))`.
- `_project_summary` gains `"kind": p.kind`; `_settings_project` too.

`reconvene/tui.py`:

- Import `from .cluster import load_topic_lookup`; in `run_tui` replace `build_journal(sessions, config)` with `build_journal(sessions, config, topic_lookup=load_topic_lookup(cache_path))`.
- `render_line` becomes:

```python
def render_line(project) -> str:
    line = f"{project.name} · {relative_time(project.last_active)} · {project.count} sessions"
    if project.kind == "topic":
        line += " · topic"
    elif project.kind == "loose":
        line += " · unorganized"
    return line
```

`reconvene/_preview.py` — `_find_project` signature gains the cache path (its caller `main` has `cache_path` in scope):

```python
def _find_project(config, db_path, cache_path, session_id):
    from .cluster import load_topic_lookup
    real, bots = build_journal(load_sessions(db_path), config,
                               topic_lookup=load_topic_lookup(cache_path))
    return next((p for p in real + bots if p.latest.session_id == session_id), None)
```

Update the call in `main`: `project = _find_project(config, db_path, cache_path, session_id)`.

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/ -q --ignore=tests/e2e` → all pass. Then e2e: `PLAYWRIGHT_BROWSERS_PATH=$(pwd)/.playwright-browsers .venv/bin/python -m pytest tests/e2e -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add reconvene/cluster.py reconvene/journal.py reconvene/web/server.py reconvene/tui.py reconvene/_preview.py tests/test_cluster.py tests/test_journal.py tests/test_web_server.py tests/test_tui.py
git commit -m "feat: root detection + sticky topic grouping of loose sessions"
```

---

### Task 10: Organize — prompt, parsing, endpoint, CLI flag, web button

**Files:**
- Modify: `reconvene/cluster.py` (prompt builder, parser, `organize`, `TopicAuthError`)
- Modify: `reconvene/web/server.py` (`POST /api/topics/refresh`)
- Modify: `reconvene/cli.py` (`--organize`)
- Modify: `reconvene/web/static/app.js` (Organize button on loose cards)
- Modify: `reconvene/web/static/style.css` (button style)
- Modify: `tests/e2e/conftest.py` (prompt-aware fake runner)
- Modify: `README.md` (document search, drill-in, `-s`, `--organize`)
- Test: `tests/test_cluster.py`, `tests/test_web_server.py`, `tests/test_cli.py`, `tests/e2e/test_journal_page.py` (append)

**Interfaces:**
- Consumes: `TopicCache`, `detect_roots` (Task 9); `first_user_message`, `claude_runner` (recap.py); `NOISE_MESSAGE_FLOOR`.
- Produces: `TopicAuthError(RuntimeError)`; `build_organize_prompt(unassigned, db_path, existing_topics) -> str`; `parse_assignments(output, valid_ids) -> dict[str, str]`; `organize(unassigned, db_path, cache, config, runner=None) -> int`; `POST /api/topics/refresh` → `{"assigned": N}` / 409 / 502; CLI `--organize`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cluster.py`:

```python
import pytest

from reconvene.cluster import (
    TopicAuthError, build_organize_prompt, organize, parse_assignments,
)
from reconvene.config import Config
from tests.conftest import add_session, add_message


def test_parse_assignments_valid_partial_and_garbage():
    output = "s1: NAS & Pi-Hole\ngarbage line\n- s2: Desktop Cleanup\nsx: Not A Session\n"
    assert parse_assignments(output, {"s1", "s2"}) == {
        "s1": "NAS & Pi-Hole", "s2": "Desktop Cleanup",
    }


def test_build_organize_prompt_includes_sessions_and_existing_topics(ccrider_db):
    add_session(ccrider_db, "l1", "/Users/x/Code", "2026-07-08 00:00:00",
                message_count=20, summary="nas work")
    add_message(ccrider_db, "l1", "user", "tune the synology", sequence=1)
    from reconvene.db import load_sessions
    (s,) = load_sessions(str(ccrider_db))
    prompt = build_organize_prompt([s], str(ccrider_db), {"Desktop Cleanup"})
    assert "l1" in prompt and "tune the synology" in prompt
    assert "Desktop Cleanup" in prompt and "nas work" in prompt


def test_organize_assigns_and_is_sticky(tmp_path, ccrider_db):
    add_session(ccrider_db, "l1", "/Users/x/Code", "2026-07-08 00:00:00", message_count=20)
    add_message(ccrider_db, "l1", "user", "pihole setup", sequence=1)
    from reconvene.db import load_sessions
    sessions = load_sessions(str(ccrider_db))
    cache = TopicCache(str(tmp_path / "r.db"))
    n = organize(sessions, str(ccrider_db), cache, Config(),
                 runner=lambda prompt: "l1: NAS & Pi-Hole")
    assert n == 1
    n2 = organize(sessions, str(ccrider_db), cache, Config(),
                  runner=lambda prompt: "l1: Different Topic")
    assert cache.get_all() == {"l1": "NAS & Pi-Hole"}   # sticky
    cache.close()


def test_organize_auth_none_raises(tmp_path, ccrider_db):
    add_session(ccrider_db, "l1", "/Users/x/Code", "2026-07-08 00:00:00", message_count=20)
    add_message(ccrider_db, "l1", "user", "hi", sequence=1)
    from reconvene.db import load_sessions
    cache = TopicCache(str(tmp_path / "r.db"))
    with pytest.raises(TopicAuthError):
        organize(load_sessions(str(ccrider_db)), str(ccrider_db), cache,
                 Config(recap_auth_mode="none"), runner=lambda p: "")
    cache.close()


def test_organize_empty_input_is_zero_and_no_claude_call(tmp_path):
    calls = []
    cache = TopicCache(str(tmp_path / "r.db"))
    assert organize([], "/nonexistent.db", cache, Config(),
                    runner=lambda p: calls.append(p) or "") == 0
    assert calls == []
    cache.close()
```

Append to `tests/test_web_server.py`:

```python
def _add_root_fixture(ccrider_db):
    for i, sub in enumerate(("alpha", "beta", "gamma")):
        add_session(ccrider_db, f"rp{i}", f"/Users/x/Code/{sub}", "2026-07-01 00:00:00", message_count=10)
        add_message(ccrider_db, f"rp{i}", "user", "work", sequence=1)
    add_session(ccrider_db, "loose1", "/Users/x/Code", "2026-07-09 00:00:00", message_count=20)
    add_message(ccrider_db, "loose1", "user", "pihole things", sequence=1)


def test_topics_refresh_assigns_and_journal_shows_topic(running_server, ccrider_db):
    base_url, _, _ = running_server
    _add_root_fixture(ccrider_db)
    req = urllib.request.Request(f"{base_url}/api/topics/refresh", method="POST")
    with urllib.request.urlopen(req) as resp:
        assert json.loads(resp.read()) == {"assigned": 1}
    with urllib.request.urlopen(f"{base_url}/api/journal") as resp:
        data = json.loads(resp.read())
    topic = next(p for p in data["real"] if p["kind"] == "topic")
    assert topic["name"] == "Homelab Fixes"


def test_topics_refresh_auth_none_is_409(running_server, ccrider_db):
    base_url, _, config = running_server
    _add_root_fixture(ccrider_db)
    config.recap_auth_mode = "none"
    req = urllib.request.Request(f"{base_url}/api/topics/refresh", method="POST")
    with pytest.raises(HTTPError) as exc:
        urllib.request.urlopen(req)
    assert exc.value.code == 409
```

Also modify the `running_server` fixture's fake runner to be prompt-aware:

```python
    def fake_recap_runner(prompt):
        if "organizing loose" in prompt:
            return "\n".join(f"{sid}: Homelab Fixes"
                             for sid in ("loose1",) if sid in prompt)
        return "ONELINE: test recap\nDETAIL: test"
```

Append to `tests/test_cli.py`:

```python
def test_main_organize_flag_runs_and_exits(tmp_path, capsys, monkeypatch, ccrider_db):
    from tests.conftest import add_session, add_message
    for i, sub in enumerate(("alpha", "beta", "gamma")):
        add_session(ccrider_db, f"rp{i}", f"/Users/x/Code/{sub}", "2026-07-01 00:00:00", message_count=10)
        add_message(ccrider_db, f"rp{i}", "user", "work", sequence=1)
    add_session(ccrider_db, "loose1", "/Users/x/Code", "2026-07-09 00:00:00", message_count=20)
    add_message(ccrider_db, "loose1", "user", "pihole things", sequence=1)
    monkeypatch.setattr("reconvene.cluster.claude_runner",
                        lambda prompt, config: "loose1: Homelab Fixes")
    rc = main(["--no-sync", "--db", str(ccrider_db), "--cache", str(tmp_path / "r.db"),
               "--config", str(tmp_path / "c.json"), "--organize"],
              stdin_isatty=True, input_fn=lambda _: "1")
    assert rc == 0
    assert "Homelab Fixes" in capsys.readouterr().out
```

(Note: the chooser must NOT run for `--organize`; `input_fn` present only for signature compatibility.)

Append to `tests/e2e/test_journal_page.py`:

```python
def test_organize_button_clusters_loose_sessions(page, e2e_server, ccrider_db):
    base_url, _, _, _ = e2e_server
    for i, sub in enumerate(("alpha", "beta", "gamma")):
        add_session(ccrider_db, f"rp{i}", f"/Users/x/Code/{sub}", "2026-07-01 00:00:00", message_count=10)
        add_message(ccrider_db, f"rp{i}", "user", "work", sequence=1)
    add_session(ccrider_db, "loose1", "/Users/x/Code", "2026-07-09 00:00:00", message_count=20)
    add_message(ccrider_db, "loose1", "user", "pihole things", sequence=1)

    page.goto(base_url)
    button = page.locator(".organize-btn")
    button.wait_for()
    button.click()
    page.get_by_text("Homelab Fixes").wait_for()
```

And update `tests/e2e/conftest.py`'s `fake_recap_runner` the same prompt-aware way as `running_server`'s (return `"loose1: Homelab Fixes"` when `"organizing loose"` is in the prompt).

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_cluster.py tests/test_web_server.py tests/test_cli.py -q` — new tests FAIL (imports missing / 404).

- [ ] **Step 3: Implement**

`reconvene/cluster.py` — append:

```python
from .recap import claude_runner, first_user_message  # noqa: E402  (module-level, after cache defs)


class TopicAuthError(RuntimeError):
    pass


ORGANIZE_PROMPT = (
    "You are organizing loose coding-assistant sessions (all launched from a generic root "
    "directory, not a project folder) into small named topic groups.\n\n"
    "Existing topics — reuse one when it fits:\n{existing}\n\n"
    "Sessions (id, date, first message, optional summary):\n{sessions}\n\n"
    "Respond with EXACTLY one line per session, in the format:\n"
    "<session_id>: <Topic Name>\n"
    "Topic names are 2-4 words, Title Case. Output nothing else."
)


def build_organize_prompt(unassigned, db_path, existing_topics) -> str:
    blocks = []
    for s in unassigned:
        first = first_user_message(db_path, s.session_id, limit=200)
        line = f"- {s.session_id} ({s.updated_at[:10]}): {first}"
        summary = (s.summary or "").replace("\n", " ").strip()
        if summary:
            line += f" | summary: {summary[:200]}"
        blocks.append(line)
    existing = "\n".join(f"- {t}" for t in sorted(existing_topics)) or "(none yet)"
    return ORGANIZE_PROMPT.format(existing=existing, sessions="\n".join(blocks))


def parse_assignments(output, valid_ids) -> dict[str, str]:
    out = {}
    for line in output.splitlines():
        sid, sep, topic = line.partition(":")
        sid, topic = sid.strip().lstrip("- ").strip(), topic.strip()
        if sep and topic and sid in valid_ids:
            out[sid] = topic
    return out


def organize(unassigned, db_path, cache, config, runner=None) -> int:
    # One claude call assigns every unassigned loose session to a topic. Existing cache rows are
    # never touched (assign is INSERT OR IGNORE). Returns how many sessions got assigned.
    if config.recap_auth_mode == "none":
        raise TopicAuthError(
            "topic clustering needs Claude — recap auth mode is 'none' (change it in Settings)"
        )
    if not unassigned:
        return 0
    run = runner or (lambda prompt: claude_runner(prompt, config))
    output = run(build_organize_prompt(unassigned, db_path, cache.topics()))
    assigned = parse_assignments(output, {s.session_id for s in unassigned})
    for sid, topic in assigned.items():
        cache.assign(sid, topic)
    return len(assigned)
```

(Move the `from .recap import …` line up into the module's import block at the top of the file — module-level imports belong together; no circular import: recap does not import cluster.)

Also add a shared helper (used by both the endpoint and the CLI):

```python
def unassigned_loose_sessions(sessions, lookup):
    from .constants import NOISE_MESSAGE_FLOOR
    roots = detect_roots({s.project_path for s in sessions})
    return [
        s for s in sessions
        if s.project_path.rstrip("/") in roots
        and s.session_id not in lookup
        and s.message_count > NOISE_MESSAGE_FLOOR
    ]
```

(Put the `NOISE_MESSAGE_FLOOR` import at module top with the other constants import.)

`reconvene/web/server.py` — import `from ..cluster import TopicAuthError, TopicCache, organize, unassigned_loose_sessions`; in `do_POST`, before the 404 fallthrough:

```python
            if path == "/api/topics/refresh":
                sessions = load_sessions(db_path)
                cache = TopicCache(cache_path)
                try:
                    unassigned = unassigned_loose_sessions(sessions, cache.get_all())
                    try:
                        n = organize(unassigned, db_path, cache, config, runner=recap_runner)
                    except TopicAuthError as e:
                        self._send_json(409, {"error": str(e)})
                        return
                    except Exception as e:
                        self._send_json(502, {"error": f"clustering failed: {e}"})
                        return
                finally:
                    cache.close()
                self._send_json(200, {"assigned": n})
                return
```

`reconvene/cli.py`:

- Flag: `ap.add_argument("--organize", action="store_true", help="cluster loose (root-launched) sessions into topics and exit")`
- After the sync block, before the frontend dispatch:

```python
    if args.organize:
        from .cluster import TopicAuthError, TopicCache, organize, unassigned_loose_sessions
        from .db import load_sessions
        sessions = load_sessions(args.db)
        cache = TopicCache(args.cache)
        try:
            unassigned = unassigned_loose_sessions(sessions, cache.get_all())
            try:
                n = organize(unassigned, args.db, cache, config, runner=None)
            except TopicAuthError as e:
                print(f"error: {e}", file=sys.stderr)
                return 1
            except Exception as e:
                print(f"error: clustering failed: {e}", file=sys.stderr)
                return 1
            lookup = cache.get_all()
        finally:
            cache.close()
        by_topic: dict[str, int] = {}
        for s in unassigned:
            topic = lookup.get(s.session_id)
            if topic:
                by_topic[topic] = by_topic.get(topic, 0) + 1
        print(f"assigned {n} session{'s' if n != 1 else ''}")
        for topic, count in sorted(by_topic.items()):
            print(f"  {topic}: {count}")
        return 0
```

(`config = load_config(args.config)` must run before this block — move the existing `config = load_config(args.config)` line above the organize block; the mode chooser must NOT run for `--organize`, so this block sits before `mode` is computed. `load_sessions` import is local to avoid an unused top-level import in the web-only path.)

`reconvene/web/static/app.js` — in `loadJournal`'s card loop, after `div.append(dot, nameEl, countEl);`:

```js
    if (project.kind === "topic") {
      const tag = document.createElement("span");
      tag.className = "kind-tag";
      tag.textContent = "topic";
      div.appendChild(tag);
    }
    if (project.kind === "loose") {
      const btn = document.createElement("button");
      btn.className = "organize-btn";
      btn.textContent = "Organize into topics";
      btn.addEventListener("click", async (e) => {
        e.stopPropagation(); // don't open the resume modal
        btn.disabled = true;
        btn.textContent = "Organizing…";
        const res = await fetch("/api/topics/refresh", { method: "POST" });
        if (!res.ok) {
          const data = await res.json();
          showError(`Organize failed: ${data.error}`);
          btn.disabled = false;
          btn.textContent = "Organize into topics";
          return;
        }
        loadJournal();
      });
      div.appendChild(btn);
    }
```

`style.css` — append:

```css
/* Topic groups */
.kind-tag {
  margin-left: 8px;
  padding: 1px 7px;
  font-size: 0.75em;
  border: 1px solid var(--dot-recent);
  border-radius: 10px;
  vertical-align: middle;
}
.organize-btn {
  float: right;
  font: inherit;
  font-size: 0.85em;
  padding: 3px 10px;
  cursor: pointer;
  color: inherit;
  background: var(--card-bg);
  border: 1px solid var(--dot-active);
  border-radius: 6px;
}
```

`README.md` — in Usage, extend the command block and prose:

```bash
reconvene -s "nas"     # jump straight into full-text session search (TUI)
reconvene --organize   # cluster loose (root-launched) sessions into named topics
```

And add after the existing Usage prose:

```markdown
**Search** (web: the box in the top bar · TUI: `ctrl-f`, or `-s` from the shell) runs
full-text search over every session's message text, using the FTS index ccrider
already maintains. **Drill-in** lets you resume any session, not just a project's
latest: click a project card and pick from its session list (web), or press `ctrl-s`
on a project (TUI). Sessions launched from a bare root directory like `~/Code` are
collected separately; hit **Organize into topics** (web) or `reconvene --organize`
to have Claude cluster them into named topic groups (assignments are cached and
never reshuffled).
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/ -q --ignore=tests/e2e` → all pass.
Run: `PLAYWRIGHT_BROWSERS_PATH=$(pwd)/.playwright-browsers .venv/bin/python -m pytest tests/e2e -q` → all pass.

- [ ] **Step 5: Commit**

```bash
git add reconvene/cluster.py reconvene/web/server.py reconvene/cli.py reconvene/web/static/app.js reconvene/web/static/style.css tests/test_cluster.py tests/test_web_server.py tests/test_cli.py tests/e2e/test_journal_page.py tests/e2e/conftest.py README.md
git commit -m "feat: explicit organize step clusters loose sessions into sticky topics"
```

---

### Task 11: Full-suite verification + live smoke test

**Files:**
- No new files; fixes only if something surfaces.

- [ ] **Step 1: Full suite**

```bash
.venv/bin/python -m pytest tests/ -q
PLAYWRIGHT_BROWSERS_PATH=$(pwd)/.playwright-browsers .venv/bin/python -m pytest tests/e2e -q
```
Expected: everything passes.

- [ ] **Step 2: Live smoke against the real ccrider DB (read-only, no claude)**

```bash
.venv/bin/python -c "
from reconvene.search import search_sessions
hits = search_sessions('$HOME/.config/ccrider/sessions.db', 'pi-hole nas')
assert hits and hits[0].session_id == 'a6064e57-20c3-49b2-a522-cb2a23b0a32e', hits[:1]
print('search OK:', hits[0].session_id, hits[0].hits, 'hits')
from reconvene.cluster import detect_roots
from reconvene.db import load_sessions
roots = detect_roots({s.project_path for s in load_sessions('$HOME/.config/ccrider/sessions.db')})
print('roots detected:', sorted(roots))
"
```
Expected: search returns the known NAS/Pi-Hole session first; roots include `/Users/saley/Code`.

- [ ] **Step 3: Commit any fixes; hand off**

Use superpowers:finishing-a-development-branch (report state to Skyler first — TUI live checks like fzf `change:reload` behavior need his terminal).

---

## Self-Review Notes

- Spec §1 sanitization, markers, missing-index error → Task 1. Unfiltered search → Task 2 (raw `load_sessions` resume) + no classification filter in `search_sessions`.
- Spec §2 web modal list (single-session projects show no list) → Task 5; TUI ctrl-s → Task 7; session preview mode → Task 6.
- Spec §3 root rule incl. worktree exclusion → Task 9 (`detect_roots` tests cover ≥3 boundary, segment alignment, worktree children, candidate-must-be-session-path); stickiness via `INSERT OR IGNORE` → Tasks 9–10; organize 409/502/fallback → Task 10; `hidden_names` on topic name → Task 9.
- Type consistency: picker protocol `(key, chosen)` defined in Task 7 and reused in Task 8; `kind` field defined Task 9, consumed Tasks 9–10; `SNIPPET_OPEN/CLOSE` from Task 1 used in Tasks 3 (client splits on the literal characters) and 6.
- Known judgment calls the implementer should NOT "fix": search results intentionally bypass classification; `/api/resume` intentionally widened to all sessions; `build_settings_projects` shows loose/topic groups like any project.
