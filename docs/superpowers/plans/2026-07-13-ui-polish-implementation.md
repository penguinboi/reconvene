# UI Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-skin Reconvene's two pages (journal, settings) with the approved "Terminal" visual
direction — a GitHub-dark-lineage color palette that follows system light/dark preference, a
mono/sans typography pairing, a recency-dot + blinking-cursor signature, and styled loading/empty
states — without changing any route, DOM id, or backend behavior.

**Architecture:** One small pure function (`recency_bucket`) computes real classification data
server-side; the HTTP layer exposes it as one new JSON field; the frontend renders it via a CSS
class. Everything else is CSS plus minimal additive markup (a dot span, a cursor span, an
empty-state message) — no restructuring of existing elements that `app.js`/`settings.js`/the
existing E2E test suite already select against.

**Tech Stack:** Python 3.11+ stdlib (`datetime`), vanilla JS/CSS (no build step, no webfonts, no
new dependency), pytest + Playwright (existing test stack).

## Global Constraints

- No manual light/dark toggle — system preference (`prefers-color-scheme`) only.
- No new runtime dependency (no webfonts, no icon library, no CSS/JS framework).
- No layout/IA changes — same pages, same routes, same DOM structure/IDs that `app.js`/
  `settings.js` and the existing E2E tests already select against. Additive markup only (new
  spans/classes), never renaming or removing an existing id/class that a test or script selects.
- Color tokens (from the approved spec, `docs/superpowers/specs/2026-07-13-ui-polish-design.md`):

  | Token | Dark | Light |
  |---|---|---|
  | `--bg` | `#0d1117` | `#ffffff` |
  | `--card-bg` | `#161b22` | `#f6f8fa` |
  | `--border` | `#30363d` | `#d0d7de` |
  | `--text` | `#e6edf3` | `#1f2328` |
  | `--text-muted` | `#8b949e` | `#57606a` |
  | `--accent` | `#238636` | `#1a7f37` |
  | `--accent-hover` | `#2ea043` | `#22903f` |
  | `--link` | `#58a6ff` | `#0969da` |
  | `--dot-active` | `#3fb950` | `#1a7f37` |
  | `--dot-recent` | `#d29922` | `#9a6700` |
  | `--dot-stale` | `--text-muted` | `--text-muted` |
  | `--error-bg` | `#3d1418` | `#fdecea` |
  | `--error-text` | `#ffb3ad` | `#611a15` |
  | `--error-border` | `#6e2530` | `#f5c6cb` |

- Typography: headings and the wordmark use `ui-monospace, "SF Mono", Menlo, monospace`; body copy
  uses `-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`; metadata (counts,
  recency) is monospace and muted.
- Recency thresholds: `<= 24h` → `active`, `<= 7 days` → `recent`, else `stale`.
- Cursor animation must respect `prefers-reduced-motion: reduce` (no animation when set).

---

### Task 1: `recency_bucket` — pure classification function

**Files:**
- Modify: `reconvene/journal.py`
- Test: `tests/test_journal.py`

**Interfaces:**
- Produces: `recency_bucket(last_active: str, now: datetime | None = None) -> str`, returning
  `"active"`, `"recent"`, or `"stale"`. `last_active` is the same `"YYYY-MM-DD HH:MM:SS"` string
  format already used by `Project.last_active` / `Session.updated_at` (see `tests/test_journal.py`'s
  existing `S()` helper). `now` defaults to `datetime.now()` when omitted, and is injectable for
  deterministic tests — mirrors the existing `claude_runner(..., model=MODEL)` /
  `open_terminal_and_resume(..., runner=subprocess.run)` pattern of injectable defaults already
  used elsewhere in this codebase.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_journal.py` (after the existing imports, keep the existing `S()` helper and
tests untouched):

```python
from datetime import datetime

from reconvene.journal import build_journal, recency_bucket
```

(This replaces the existing `from reconvene.journal import build_journal` import line — just add
`recency_bucket` to it.)

Add these new test functions anywhere after the existing ones in the same file:

```python
def test_recency_bucket_active_within_24_hours():
    now = datetime(2026, 7, 13, 12, 0, 0)
    assert recency_bucket("2026-07-13 00:00:00", now=now) == "active"


def test_recency_bucket_active_at_exactly_24_hours():
    now = datetime(2026, 7, 13, 12, 0, 0)
    assert recency_bucket("2026-07-12 12:00:00", now=now) == "active"


def test_recency_bucket_recent_just_past_24_hours():
    now = datetime(2026, 7, 13, 12, 0, 0)
    assert recency_bucket("2026-07-12 11:59:59", now=now) == "recent"


def test_recency_bucket_recent_at_exactly_7_days():
    now = datetime(2026, 7, 13, 12, 0, 0)
    assert recency_bucket("2026-07-06 12:00:00", now=now) == "recent"


def test_recency_bucket_stale_just_past_7_days():
    now = datetime(2026, 7, 13, 12, 0, 0)
    assert recency_bucket("2026-07-06 11:59:59", now=now) == "stale"


def test_recency_bucket_stale_long_ago():
    now = datetime(2026, 7, 13, 12, 0, 0)
    assert recency_bucket("2020-01-01 00:00:00", now=now) == "stale"


def test_recency_bucket_defaults_now_to_current_time():
    # No `now` passed — exercises the real datetime.now() default path.
    recent = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    assert recency_bucket(recent) == "active"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Code/penguinboisoftware/reconvene && .venv/bin/pytest tests/test_journal.py -v`
Expected: the 7 new tests FAIL with `ImportError: cannot import name 'recency_bucket'`.

- [ ] **Step 3: Implement `recency_bucket`**

In `reconvene/journal.py`, add the import and function. The file currently starts:

```python
# ABOUTME: Rolls classified sessions into ranked per-project journal entries.
# ABOUTME: Real projects and bot projects are returned as two separately-sorted lists.
from dataclasses import dataclass

from .classify import classify_category, canonical_name
from .db import Session
```

Change the top of the file to:

```python
# ABOUTME: Rolls classified sessions into ranked per-project journal entries.
# ABOUTME: Real projects and bot projects are returned as two separately-sorted lists.
from dataclasses import dataclass
from datetime import datetime

from .classify import classify_category, canonical_name
from .db import Session
```

Add this function after the `Project` class and before `build_journal`:

```python
def recency_bucket(last_active: str, now: datetime | None = None) -> str:
    now = now or datetime.now()
    updated = datetime.strptime(last_active, "%Y-%m-%d %H:%M:%S")
    delta = (now - updated).total_seconds()
    if delta <= 24 * 3600:
        return "active"
    if delta <= 7 * 24 * 3600:
        return "recent"
    return "stale"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/Code/penguinboisoftware/reconvene && .venv/bin/pytest tests/test_journal.py -v`
Expected: all tests PASS (existing `test_build_journal_*` tests plus the 7 new `recency_bucket`
tests).

- [ ] **Step 5: Commit**

```bash
cd ~/Code/penguinboisoftware/reconvene
git add reconvene/journal.py tests/test_journal.py
git commit -m "feat: add recency_bucket for classifying project activity age"
```

---

### Task 2: Expose `recency` in the journal API response

**Files:**
- Modify: `reconvene/web/server.py`
- Test: `tests/test_web_server.py`

**Interfaces:**
- Consumes: `recency_bucket(last_active, now=None)` from Task 1.
- Produces: `_project_summary(p, db_path)` now includes a `"recency"` key (one of `"active"` /
  `"recent"` / `"stale"`) in its returned dict — consumed by the frontend in Task 4.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_web_server.py`, right after `test_settings_post_saves_terminal_app_and_extra_args`
(same file already imports `threading`, `urllib.request`, `json`, `Config`, `serve`,
`add_session`, `add_message` — no new imports needed):

```python
def test_api_journal_includes_recency_bucket(tmp_path, ccrider_db):
    add_session(ccrider_db, "r1", "/Users/x/Code/myproject", "2020-01-01 00:00:00", message_count=12)
    add_message(ccrider_db, "r1", "user", "wire up thresholds", sequence=1)
    config = Config()
    fake_recap_runner = lambda prompt: "ONELINE: test recap\nDETAIL: test"
    server = serve(config, str(ccrider_db), str(tmp_path / "recaps.db"), str(tmp_path / "config.json"),
                   lambda s, c: None, recap_runner=fake_recap_runner, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        with urllib.request.urlopen(f"{base_url}/api/journal") as resp:
            data = json.loads(resp.read())
        assert data["real"][0]["recency"] == "stale"
    finally:
        server.shutdown()
        server.server_close()
```

(Uses a fixed `2020-01-01` timestamp rather than the shared `running_server` fixture's
`2026-07-08` date — that date is shared by other tests and, being close to "now", would make this
new assertion flaky as real time passes. `2020-01-01` is unambiguously `stale` regardless of when
the suite runs.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/Code/penguinboisoftware/reconvene && .venv/bin/pytest tests/test_web_server.py::test_api_journal_includes_recency_bucket -v`
Expected: FAIL with `KeyError: 'recency'`.

- [ ] **Step 3: Implement**

In `reconvene/web/server.py`, the current import line is:

```python
from ..recap import RecapCache, ensure_recaps, first_user_message
```

Change it to also import `recency_bucket` from `journal`:

```python
from ..journal import build_journal, recency_bucket
from ..recap import RecapCache, ensure_recaps, first_user_message
```

(`build_journal` is already imported elsewhere in this file — check the existing import block; if
there is already a line `from ..journal import build_journal`, replace that single line with the
combined one above rather than adding a duplicate import.)

Change `_project_summary`:

```python
def _project_summary(p, db_path):
    return {
        "name": p.name,
        "category": p.category,
        "count": p.count,
        "last_active": p.last_active,
        "recency": recency_bucket(p.last_active),
        "latest_session_id": p.latest.session_id,
        "oneline": first_user_message(db_path, p.latest.session_id) or "(no recap)",
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/Code/penguinboisoftware/reconvene && .venv/bin/pytest tests/test_web_server.py -v`
Expected: all tests PASS, including the new one.

- [ ] **Step 5: Commit**

```bash
cd ~/Code/penguinboisoftware/reconvene
git add reconvene/web/server.py tests/test_web_server.py
git commit -m "feat: expose recency bucket in the journal API response"
```

---

### Task 3: Re-theme `style.css` — color tokens, typography, components

**Files:**
- Modify: `reconvene/web/static/style.css`

**Interfaces:**
- Consumes: nothing new from prior tasks — pure CSS.
- Produces: CSS custom properties (`--bg`, `--card-bg`, `--border`, `--text`, `--text-muted`,
  `--accent`, `--accent-hover`, `--link`, `--dot-active`, `--dot-recent`, `--dot-stale`,
  `--error-bg`, `--error-text`, `--error-border`) and the classes `.dot`, `.dot-active`,
  `.dot-recent`, `.dot-stale`, `.cursor`, `.placeholder` that Task 4's markup will use. Existing
  classes (`.project`, `.project .meta`, `.error`, `.modal`, `.modal.hidden`, `.modal-content`)
  keep their exact names — only their declarations change.

**No automated test for this task** — it is pure CSS with no logic to unit test. The existing
Playwright E2E suite asserts on text content, element ids/classes, and structural state (visible/
hidden), never on computed color/font — so it is the correct regression check for "did this break
anything," and gets run at the end of this task. Visual correctness is verified by hand: starting
the real server and loading both pages in a browser (Step 3 below).

- [ ] **Step 1: Replace the file contents**

Replace the entire contents of `reconvene/web/static/style.css` with:

```css
:root {
  --bg: #ffffff;
  --card-bg: #f6f8fa;
  --border: #d0d7de;
  --text: #1f2328;
  --text-muted: #57606a;
  --accent: #1a7f37;
  --accent-hover: #22903f;
  --link: #0969da;
  --dot-active: #1a7f37;
  --dot-recent: #9a6700;
  --dot-stale: #57606a;
  --error-bg: #fdecea;
  --error-text: #611a15;
  --error-border: #f5c6cb;
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0d1117;
    --card-bg: #161b22;
    --border: #30363d;
    --text: #e6edf3;
    --text-muted: #8b949e;
    --accent: #238636;
    --accent-hover: #2ea043;
    --link: #58a6ff;
    --dot-active: #3fb950;
    --dot-recent: #d29922;
    --dot-stale: #8b949e;
    --error-bg: #3d1418;
    --error-text: #ffb3ad;
    --error-border: #6e2530;
  }
}

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  max-width: 720px;
  margin: 2rem auto;
  padding: 0 1rem;
  background: var(--bg);
  color: var(--text);
}

h1, h2 {
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
}

a {
  color: var(--link);
}

.cursor {
  display: inline-block;
  animation: blink 1s steps(1) infinite;
}

@keyframes blink {
  0%, 49% { opacity: 1; }
  50%, 100% { opacity: 0; }
}

@media (prefers-reduced-motion: reduce) {
  .cursor { animation: none; }
}

.dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 0.5rem;
}

.dot-active { background: var(--dot-active); }
.dot-recent { background: var(--dot-recent); }
.dot-stale { background: var(--dot-stale); }

.project {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0.75rem 1rem;
  margin-bottom: 0.5rem;
  cursor: pointer;
}

.project:hover {
  filter: brightness(1.1);
}

.project .meta {
  color: var(--text-muted);
  font-size: 0.85rem;
  margin-top: 0.35rem;
}

.project .count {
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
  color: var(--text-muted);
  font-size: 0.85rem;
}

.placeholder {
  color: var(--text-muted);
  text-align: center;
  padding: 2rem 0;
}

.error {
  background: var(--error-bg);
  color: var(--error-text);
  border: 1px solid var(--error-border);
  border-radius: 6px;
  padding: 0.5rem 0.75rem;
  margin-bottom: 1rem;
}

button {
  background: var(--accent);
  color: white;
  border: none;
  border-radius: 6px;
  padding: 0.5rem 1rem;
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  font-family: inherit;
}

button:hover {
  background: var(--accent-hover);
}

input[type="text"], select, textarea {
  background: var(--card-bg);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0.4rem 0.6rem;
  font-family: inherit;
  font-size: 0.9rem;
}

input[type="text"]:focus, select:focus, textarea:focus {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
}

table {
  border-collapse: collapse;
  width: 100%;
  margin-bottom: 1rem;
}

table td, table th {
  border: 1px solid var(--border);
  padding: 0.5rem 0.75rem;
  text-align: left;
}

.modal {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
}

.modal.hidden {
  display: none;
}

.modal-content {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 1.5rem;
  max-width: 640px;
  max-height: 80vh;
  overflow-y: auto;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.4);
}

.modal-content p {
  white-space: pre-wrap;
  color: var(--text-muted);
}
```

- [ ] **Step 2: Run the existing suite to confirm no regressions**

Run: `cd ~/Code/penguinboisoftware/reconvene && PLAYWRIGHT_BROWSERS_PATH=$(pwd)/.playwright-browsers .venv/bin/pytest tests/ -q`
Expected: all tests still PASS — this task changed no markup, ids, or classes that any test
selects on.

- [ ] **Step 3: Manually verify in a real browser**

```bash
cd ~/Code/penguinboisoftware/reconvene
.venv/bin/reconvene &
```

Open `http://127.0.0.1:4242` (or whatever port it printed). Confirm: dark background if your
system is in dark mode (or light if in light mode), styled buttons (solid green, not the browser
default), styled inputs/select on the Settings page, monospace headings. Then stop the background
process (`kill %1` or `fg` + Ctrl-C).

- [ ] **Step 4: Commit**

```bash
cd ~/Code/penguinboisoftware/reconvene
git add reconvene/web/static/style.css
git commit -m "style: re-theme with Terminal palette, system light/dark, mono/sans pairing"
```

---

### Task 4: Recency dot, cursor, and empty-state markup

**Files:**
- Modify: `reconvene/web/static/index.html`
- Modify: `reconvene/web/static/app.js`
- Test: `tests/e2e/test_journal_page.py`

**Interfaces:**
- Consumes: `recency` field from Task 2's `/api/journal` response; `.dot`/`.dot-active`/
  `.dot-recent`/`.dot-stale`/`.cursor`/`.placeholder` classes from Task 3.
- Produces: no new interfaces for later tasks — this is the last task.

- [ ] **Step 1: Write the failing tests**

Add to `tests/e2e/test_journal_page.py`. First, add the `datetime`/`timedelta` import at the top
of the file (alongside the existing `import threading` / `import time`):

```python
from datetime import datetime, timedelta
```

Then add these two test functions (anywhere after `test_journal_renders_project_card`):

```python
def test_journal_shows_empty_state_when_no_real_projects(page, e2e_server):
    base_url, resumed, config, config_path = e2e_server

    page.goto(base_url)
    placeholder = page.locator(".placeholder")
    placeholder.wait_for()
    assert "resume some Claude Code sessions" in placeholder.inner_text()
    assert page.locator(".project").count() == 0


def test_journal_renders_recency_dots(page, e2e_server, ccrider_db):
    now = datetime.now()
    add_session(ccrider_db, "s1", "/Users/x/Code/activeproject",
                now.strftime("%Y-%m-%d %H:%M:%S"), message_count=12)
    add_message(ccrider_db, "s1", "user", "wire up thresholds", sequence=1)
    add_session(ccrider_db, "s2", "/Users/x/Code/staleproject",
                (now - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S"), message_count=12)
    add_message(ccrider_db, "s2", "user", "old work", sequence=1)

    base_url, resumed, config, config_path = e2e_server
    page.goto(base_url)
    page.locator(".project").first.wait_for()

    active_card = page.locator(".project", has_text="activeproject")
    stale_card = page.locator(".project", has_text="staleproject")
    assert active_card.locator(".dot-active").count() == 1
    assert stale_card.locator(".dot-stale").count() == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/Code/penguinboisoftware/reconvene && PLAYWRIGHT_BROWSERS_PATH=$(pwd)/.playwright-browsers .venv/bin/pytest tests/e2e/test_journal_page.py -v -k "empty_state or recency_dots"`
Expected: `test_journal_shows_empty_state_when_no_real_projects` FAILS (no `.placeholder` element
exists yet — `loadJournal` currently leaves `#journal` empty when `data.real` is `[]`).
`test_journal_renders_recency_dots` FAILS (no `.dot-active`/`.dot-stale` elements exist yet).

- [ ] **Step 3: Update `index.html`**

Current `reconvene/web/static/index.html` body:

```html
<body>
  <h1>Reconvene</h1>
  <div id="journal">Loading…</div>
  <a href="/settings.html">Settings</a>
  <div id="confirmModal" class="modal hidden">
    <div class="modal-content">
      <h2 id="modalProjectName"></h2>
      <p id="modalFullRecap"></p>
      <button id="modalConfirm">Resume</button>
      <button id="modalCancel">Cancel</button>
    </div>
  </div>
  <script src="/app.js"></script>
</body>
```

Change the `<h1>` line and the loading placeholder's styling class (text stays the same — `#journal`
still starts with "Loading…" as its initial static content, restyled by the `.placeholder` class
already defined in Task 3):

```html
<body>
  <h1>Reconvene<span class="cursor">▊</span></h1>
  <div id="journal" class="placeholder">Loading…</div>
  <a href="/settings.html">Settings</a>
  <div id="confirmModal" class="modal hidden">
    <div class="modal-content">
      <h2 id="modalProjectName"></h2>
      <p id="modalFullRecap"></p>
      <button id="modalConfirm">Resume</button>
      <button id="modalCancel">Cancel</button>
    </div>
  </div>
  <script src="/app.js"></script>
</body>
```

- [ ] **Step 4: Update `app.js`**

Current `loadJournal` in `reconvene/web/static/app.js`:

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
    div.addEventListener("click", () => showConfirmModal(project));
    el.appendChild(div);
    fetch(`/api/recap/${project.name}`)
      .then((r) => r.json())
      .then((recap) => {
        metaEl.textContent = recap.oneline;
        fullRecaps.set(project.name, recap.full);
        const modal = document.getElementById("confirmModal");
        if (!modal.classList.contains("hidden") && modal.dataset.projectName === project.name) {
          document.getElementById("modalFullRecap").textContent = recap.full;
        }
      })
      .catch((err) => console.error(`Failed to fetch recap for ${project.name}:`, err));
  }
}
```

Replace it with (adds the empty-state branch, removes `.placeholder` once real content renders,
and adds the recency dot + a `.count` span for the session count):

```javascript
async function loadJournal() {
  const res = await fetch("/api/journal");
  const data = await res.json();
  const el = document.getElementById("journal");
  el.innerHTML = "";
  el.classList.remove("placeholder");

  if (data.real.length === 0) {
    el.classList.add("placeholder");
    el.textContent = "No projects yet — resume some Claude Code sessions and they'll show up here.";
    return;
  }

  for (const project of data.real) {
    const div = document.createElement("div");
    div.className = "project";
    div.dataset.sessionId = project.latest_session_id;
    const metaEl = document.createElement("div");
    metaEl.className = "meta";
    metaEl.textContent = project.oneline;
    div.innerHTML = `<span class="dot dot-${project.recency}"></span>` +
      `<strong>${project.name}</strong> <span class="count">· ${project.count} sessions</span>`;
    div.appendChild(metaEl);
    div.addEventListener("click", () => showConfirmModal(project));
    el.appendChild(div);
    fetch(`/api/recap/${project.name}`)
      .then((r) => r.json())
      .then((recap) => {
        metaEl.textContent = recap.oneline;
        fullRecaps.set(project.name, recap.full);
        const modal = document.getElementById("confirmModal");
        if (!modal.classList.contains("hidden") && modal.dataset.projectName === project.name) {
          document.getElementById("modalFullRecap").textContent = recap.full;
        }
      })
      .catch((err) => console.error(`Failed to fetch recap for ${project.name}:`, err));
  }
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd ~/Code/penguinboisoftware/reconvene && PLAYWRIGHT_BROWSERS_PATH=$(pwd)/.playwright-browsers .venv/bin/pytest tests/e2e/test_journal_page.py -v`
Expected: all tests PASS, including the two new ones.

- [ ] **Step 6: Run the full suite**

Run: `cd ~/Code/penguinboisoftware/reconvene && PLAYWRIGHT_BROWSERS_PATH=$(pwd)/.playwright-browsers .venv/bin/pytest tests/ -q`
Expected: all tests PASS (full regression check across unit + HTTP + E2E suites).

- [ ] **Step 7: Manually verify in a real browser**

```bash
cd ~/Code/penguinboisoftware/reconvene
.venv/bin/reconvene &
```

Open the printed URL. Confirm: a blinking cursor after "Reconvene" (steady if your system has
"reduce motion" enabled), a colored dot before each project name (green/amber/gray depending on
how recently each was active), and — if you temporarily rename/move your ccrider DB to point at an
empty one via `--db` — the empty-state message instead of a blank page. Stop the background
process (`kill %1` or `fg` + Ctrl-C) when done.

- [ ] **Step 8: Commit**

```bash
cd ~/Code/penguinboisoftware/reconvene
git add reconvene/web/static/index.html reconvene/web/static/app.js tests/e2e/test_journal_page.py
git commit -m "feat: add recency dot, prompt cursor, and empty-state message"
```

---

## Self-Review Notes

- **Spec coverage:** color tokens (Task 3), typography pairing (Task 3), recency-dot signature
  (Tasks 1, 2, 4), blinking cursor (Tasks 3, 4), component restyling — buttons/inputs/table/
  cards/modal/error banner (Task 3), loading state (Tasks 3, 4), empty state (Task 4) — all
  covered. Settings-page table/input restyling is covered by Task 3 alone since `settings.html`'s
  existing elements (`table`, `input[type="text"]`, `select`, `textarea`, `button`) already match
  the new generic CSS selectors — no `settings.html`/`settings.js` markup changes are needed.
- **Placeholder scan:** none found — every step has concrete code.
- **Type consistency:** `recency_bucket` signature (`last_active: str, now: datetime | None = None`)
  is identical across Task 1 (definition), Task 2 (`server.py` call site), and the spec. The
  `"active"`/`"recent"`/`"stale"` string values are identical across Task 1's return values, Task
  2's test assertion, Task 3's CSS class names (`.dot-active`/`.dot-recent`/`.dot-stale`), and Task
  4's template literal (``dot-${project.recency}``).
