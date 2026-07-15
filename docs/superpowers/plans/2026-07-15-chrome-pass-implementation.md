# Chrome Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Reconvene's journal and settings pages a shared topbar, elevated/animated cards and panels, and a new per-card metadata line (last-active time + working directory) — no other functional change.

**Architecture:** Two small pure functions (`relative_time`, `abbreviate_home`) added to `journal.py` feed two new read-only fields on the existing `/api/journal` and `/api/settings` payloads; `app.js` renders them into a new `.meta-line` element. Separately, `index.html`/`settings.html` gain a shared `.topbar`, settings sections are wrapped in `.panel` divs, and `style.css` gains elevation/transition rules on top of the existing "Terminal" token system — no new tokens beyond one new `--accent-glow` pair.

**Tech Stack:** Python 3.11+ stdlib (existing `reconvene` package), vanilla JS/CSS/HTML (no new runtime dependency), pytest + Playwright (existing test stack, `.venv`).

## Global Constraints

- No new runtime dependency: no webfonts, icon library, CSS framework, or JS framework.
- No manual light/dark toggle — everything continues to follow `prefers-color-scheme` automatically.
- Any new motion (hover-lift transforms) must be dropped under `@media (prefers-reduced-motion:
  reduce)`; color/shadow transitions may still run.
- Do not change any existing DOM id/class that `app.js`, `settings.js`, or the existing E2E suite
  already selects against. New elements introduced by this plan (`.topbar`, `.topbar-home`,
  `.panel`, `.meta-line`) are additive.
- `relative_time()` must reuse `recency_bucket()`'s established timestamp-parsing fix: truncate to
  the fixed-width leading 19 characters (`last_active[:19]`) before `strptime`, and default `now`
  to `datetime.now(timezone.utc).replace(tzinfo=None)`. ccrider's real `updated_at` format
  (`"2026-07-13 10:12:17.839 +0000 UTC"`) already broke `recency_bucket` once over exactly this
  mismatch — do not reintroduce it.
- No changes to resume/recap mechanics, classification logic, or settings persistence.
- Run the venv's pytest for every verification step in this plan: `.venv/bin/python -m pytest
  <path> -v` (the system `python3` lacks `pytest-playwright`).

---

### Task 1: Metadata helpers — `relative_time()` and `abbreviate_home()`

**Files:**
- Modify: `reconvene/journal.py`
- Test: `tests/test_journal.py`

**Interfaces:**
- Produces: `relative_time(last_active: str, now: datetime | None = None) -> str` and
  `abbreviate_home(path: str, home: str | None = None) -> str`, both in `reconvene/journal.py`.
  Task 2 imports and calls both.

- [ ] **Step 1: Write the failing tests**

In `tests/test_journal.py`, change the import line:

```python
from reconvene.journal import build_journal, recency_bucket
```

to:

```python
from reconvene.journal import abbreviate_home, build_journal, recency_bucket, relative_time
```

Then append these tests at the end of the file:

```python
def test_relative_time_just_now_under_a_minute():
    now = datetime(2026, 7, 15, 12, 0, 0)
    assert relative_time("2026-07-15 11:59:30", now=now) == "just now"


def test_relative_time_minutes_ago():
    now = datetime(2026, 7, 15, 12, 0, 0)
    assert relative_time("2026-07-15 11:58:00", now=now) == "2m ago"


def test_relative_time_hours_ago():
    now = datetime(2026, 7, 15, 12, 0, 0)
    assert relative_time("2026-07-15 09:00:00", now=now) == "3h ago"


def test_relative_time_days_ago():
    now = datetime(2026, 7, 15, 12, 0, 0)
    assert relative_time("2026-07-13 12:00:00", now=now) == "2d ago"


def test_relative_time_months_ago():
    now = datetime(2026, 7, 15, 12, 0, 0)
    assert relative_time("2026-05-15 12:00:00", now=now) == "2mo ago"


def test_relative_time_years_ago():
    now = datetime(2026, 7, 15, 12, 0, 0)
    assert relative_time("2024-07-15 12:00:00", now=now) == "2y ago"


def test_relative_time_handles_real_ccrider_timestamp_format():
    # Same fractional-seconds + "+0000 UTC" format that once crashed recency_bucket
    # (see the test-fixtures-mirror-real-schema lesson) — relative_time must not
    # reintroduce that bug.
    now = datetime(2026, 7, 13, 10, 12, 20)
    assert relative_time("2026-07-13 10:12:17.839 +0000 UTC", now=now) == "just now"


def test_abbreviate_home_collapses_home_prefix():
    assert abbreviate_home("/Users/fake/Code/foo", home="/Users/fake") == "~/Code/foo"


def test_abbreviate_home_exact_home_path():
    assert abbreviate_home("/Users/fake", home="/Users/fake") == "~"


def test_abbreviate_home_leaves_unrelated_path_unchanged():
    assert abbreviate_home("/opt/other/path", home="/Users/fake") == "/opt/other/path"


def test_abbreviate_home_does_not_match_sibling_dir_with_shared_prefix():
    # "/Users/fake2" starts with the string "/Users/fake" but is a different directory —
    # must not be treated as being under "/Users/fake".
    assert abbreviate_home("/Users/fake2/Code", home="/Users/fake") == "/Users/fake2/Code"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_journal.py -k "relative_time or abbreviate_home" -v`
Expected: FAIL — `ImportError: cannot import name 'relative_time' from 'reconvene.journal'`

- [ ] **Step 3: Implement the minimal code to make the tests pass**

In `reconvene/journal.py`, change the top import line:

```python
from datetime import datetime, timezone
```

to:

```python
from datetime import datetime, timezone
from pathlib import Path
```

Then add these two functions directly below the existing `recency_bucket` function:

```python
def relative_time(last_active: str, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    updated = datetime.strptime(last_active[:19], "%Y-%m-%d %H:%M:%S")
    delta = (now - updated).total_seconds()
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{int(delta // 60)}m ago"
    if delta < 86400:
        return f"{int(delta // 3600)}h ago"
    if delta < 30 * 86400:
        return f"{int(delta // 86400)}d ago"
    if delta < 365 * 86400:
        return f"{int(delta // (30 * 86400))}mo ago"
    return f"{int(delta // (365 * 86400))}y ago"


def abbreviate_home(path: str, home: str | None = None) -> str:
    home = home if home is not None else str(Path.home())
    if path == home:
        return "~"
    if path.startswith(home + "/"):
        return "~" + path[len(home):]
    return path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_journal.py -v`
Expected: all tests PASS (existing `build_journal`/`recency_bucket` tests plus the new ones)

- [ ] **Step 5: Commit**

```bash
git add reconvene/journal.py tests/test_journal.py
git commit -m "feat: add relative_time and abbreviate_home helpers"
```

---

### Task 2: Wire metadata into the journal API

**Files:**
- Modify: `reconvene/web/server.py`
- Test: `tests/test_web_server.py`

**Interfaces:**
- Consumes: `relative_time(last_active, now=None)`, `abbreviate_home(path, home=None)` from Task 1.
- Produces: `_project_summary()` gains two new keys, `last_active_relative: str` and `cwd: str`,
  present on every project object returned by `/api/journal` and `/api/settings`. Task 3 consumes
  both from the `/api/journal` response.

- [ ] **Step 1: Write the failing test**

In `tests/test_web_server.py`, add this test after `test_api_journal_includes_recency_bucket`:

```python
def test_api_journal_includes_last_active_relative_and_cwd(tmp_path, ccrider_db):
    add_session(ccrider_db, "r1", "/tmp/some/fake/project", "2020-01-01 00:00:00", message_count=12)
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
        assert data["real"][0]["last_active_relative"].endswith("y ago")
        assert data["real"][0]["cwd"] == "/tmp/some/fake/project"
    finally:
        server.shutdown()
        server.server_close()
```

No new imports are needed — `threading`, `json`, `urllib.request`, `serve`, `Config`,
`add_session`, `add_message` are already imported at the top of this file.

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_web_server.py -k last_active_relative -v`
Expected: FAIL with `KeyError: 'last_active_relative'`

- [ ] **Step 3: Implement the minimal code to make the test pass**

In `reconvene/web/server.py`, change the import line:

```python
from ..journal import build_journal, recency_bucket
```

to:

```python
from ..journal import abbreviate_home, build_journal, recency_bucket, relative_time
```

Then update `_project_summary`:

```python
def _project_summary(p, db_path):
    return {
        "name": p.name,
        "category": p.category,
        "count": p.count,
        "last_active": p.last_active,
        "recency": recency_bucket(p.last_active),
        "last_active_relative": relative_time(p.last_active),
        "cwd": abbreviate_home(p.latest.project_path),
        "latest_session_id": p.latest.session_id,
        "oneline": first_user_message(db_path, p.latest.session_id) or "(no recap)",
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_web_server.py -v`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add reconvene/web/server.py tests/test_web_server.py
git commit -m "feat: expose last_active_relative and cwd on project summaries"
```

---

### Task 3: Render the metadata line on journal cards

**Files:**
- Modify: `reconvene/web/static/app.js`
- Modify: `reconvene/web/static/style.css`
- Test: `tests/e2e/test_journal_page.py`

**Interfaces:**
- Consumes: `project.last_active_relative`, `project.cwd` from the `/api/journal` response
  (Task 2) — both are present synchronously, no need to wait on the async `/api/recap/<name>`
  fetch.
- Produces: a `.meta-line` element inside each `.project` card, rendered before the existing
  `.meta` (recap) element. No new selectors that later tasks depend on.

- [ ] **Step 1: Write the failing test**

Add this test to `tests/e2e/test_journal_page.py`, after `test_journal_renders_recency_dots`:

```python
def test_journal_card_shows_last_active_time_and_cwd(page, e2e_server, ccrider_db):
    base_url, resumed, config, config_path = e2e_server
    add_session(ccrider_db, "s1", "/tmp/some/fake/project", "2020-01-01 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "wire up thresholds", sequence=1)

    page.goto(base_url)
    meta_line = page.locator(".project .meta-line")
    meta_line.wait_for()
    text = meta_line.inner_text()
    assert "y ago" in text
    assert "/tmp/some/fake/project" in text
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/python -m pytest tests/e2e/test_journal_page.py -k last_active_time_and_cwd -v`
Expected: FAIL — `.meta-line` never appears (timeout in `wait_for()`)

- [ ] **Step 3: Implement the minimal code to make the test pass**

In `reconvene/web/static/app.js`, replace this block inside `loadJournal()`:

```javascript
    const metaEl = document.createElement("div");
    metaEl.className = "meta";
    metaEl.textContent = project.oneline;
    div.innerHTML = `<span class="dot dot-${project.recency}"></span>` +
      `<strong>${project.name}</strong> <span class="count">· ${project.count} sessions</span>`;
    div.appendChild(metaEl);
```

with:

```javascript
    const metaLineEl = document.createElement("div");
    metaLineEl.className = "meta-line";
    metaLineEl.textContent = `${project.last_active_relative} · ${project.cwd}`;
    const metaEl = document.createElement("div");
    metaEl.className = "meta";
    metaEl.textContent = project.oneline;
    div.innerHTML = `<span class="dot dot-${project.recency}"></span>` +
      `<strong>${project.name}</strong> <span class="count">· ${project.count} sessions</span>`;
    div.appendChild(metaLineEl);
    div.appendChild(metaEl);
```

In `reconvene/web/static/style.css`, add this rule directly after the existing `.project .count`
rule:

```css
.project .meta-line {
  font-family: ui-monospace, "SF Mono", Menlo, monospace;
  color: var(--text-muted);
  font-size: 0.8rem;
  margin-top: 0.35rem;
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/bin/python -m pytest tests/e2e/test_journal_page.py -v`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add reconvene/web/static/app.js reconvene/web/static/style.css tests/e2e/test_journal_page.py
git commit -m "feat: show last-active time and cwd on journal cards"
```

---

### Task 4: Shared topbar and settings panel restructure

**Files:**
- Modify: `reconvene/web/static/index.html`
- Modify: `reconvene/web/static/settings.html`
- Modify: `reconvene/web/static/style.css`
- Test: `tests/e2e/test_journal_page.py`
- Test: `tests/e2e/test_settings_page.py`

**Interfaces:**
- Produces: `.topbar` and `.topbar-home` (both pages), `.panel` (settings sections). Task 5
  layers box-shadow/transition rules onto `.project` and this task's new `.panel` class — no
  further markup changes.
- No JS changes: `settings.js`'s existing lookups (`#projects`, `#hiddenPathSubstrings`,
  `#terminalApp`, `#claudeExtraArgs`, `#apiKey`, `#save`, `input[name="auth"]`) are untouched, only
  their surrounding wrapper markup changes.

- [ ] **Step 1: Write the failing tests**

Add this test to `tests/e2e/test_journal_page.py`, after `test_journal_renders_project_card`:

```python
def test_topbar_home_link_and_settings_nav_present(page, e2e_server):
    base_url, resumed, config, config_path = e2e_server
    page.goto(base_url)
    page.locator(".topbar").wait_for()
    assert page.locator(".topbar-home").get_attribute("href") == "/"
    assert page.locator(".topbar a", has_text="Settings").get_attribute("href") == "/settings.html"
```

Add this test to `tests/e2e/test_settings_page.py`, after the imports (as the first test in the
file):

```python
def test_topbar_journal_nav_present_on_settings(page, e2e_server):
    base_url, resumed, config, config_path = e2e_server
    page.goto(f"{base_url}/settings.html")
    page.locator(".topbar").wait_for()
    assert page.locator(".topbar a", has_text="Journal").count() == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/e2e/test_journal_page.py tests/e2e/test_settings_page.py -k topbar -v`
Expected: FAIL — `.topbar` never appears (timeout in `wait_for()`)

- [ ] **Step 3: Implement the minimal code to make the tests pass**

Replace the full contents of `reconvene/web/static/index.html` with:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Reconvene</title>
  <link rel="stylesheet" href="/style.css">
</head>
<body>
  <div class="topbar">
    <a href="/" class="topbar-home"><h1>Reconvene<span class="cursor">▊</span></h1></a>
    <a href="/settings.html">Settings</a>
  </div>
  <div id="journal" class="placeholder">Loading…</div>
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
</html>
```

Replace the full contents of `reconvene/web/static/settings.html` with:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Reconvene — Settings</title>
  <link rel="stylesheet" href="/style.css">
</head>
<body>
  <div class="topbar">
    <a href="/" class="topbar-home"><h1>Reconvene<span class="cursor">▊</span></h1></a>
    <a href="/">Journal</a>
  </div>
  <h2>Settings</h2>
  <div class="panel">
    <h2>Projects</h2>
    <table id="projects"></table>
  </div>
  <div class="panel">
    <h2>Hide by path</h2>
    <p>One substring per line. Any project whose path contains one of these is hidden entirely
       (useful for bulk-filtering a family of auto-generated directory names).</p>
    <textarea id="hiddenPathSubstrings" rows="4" cols="40" placeholder="sarb_agent_"></textarea>
  </div>
  <div class="panel">
    <h2>Recap generation</h2>
    <label><input type="radio" name="auth" value="claude_cli"> Use claude CLI login</label><br>
    <label><input type="radio" name="auth" value="api_key"> Use an API key</label>
    <input type="text" id="apiKey" placeholder="sk-..."><br>
    <label><input type="radio" name="auth" value="none"> No recaps</label>
  </div>
  <div class="panel">
    <h2>Resume</h2>
    <label>Terminal app:
      <select id="terminalApp">
        <option value="Terminal">Terminal</option>
        <option value="iTerm2">iTerm2</option>
      </select>
    </label><br>
    <label>Claude Code flags: <input type="text" id="claudeExtraArgs" placeholder="--dangerously-skip-permissions"></label>
    <p>Extra arguments appended to <code>claude --resume &lt;session&gt;</code> when opening a session.</p>
  </div>
  <button id="save">Save</button>
  <script src="/settings.js"></script>
</body>
</html>
```

In `reconvene/web/static/style.css`, add this block directly after the `@media
(prefers-reduced-motion: reduce) { .cursor { animation: none; } }` rule:

```css
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 0.75rem;
  margin-bottom: 1.5rem;
  border-bottom: 1px solid var(--border);
}

.topbar-home {
  text-decoration: none;
}

.topbar-home:hover {
  text-decoration: none;
}

.topbar h1 {
  margin: 0;
  font-size: 1.3rem;
  color: var(--text);
}

.panel {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 1rem 1.25rem;
  margin-bottom: 1rem;
}

.panel h2 {
  margin-top: 0;
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/e2e/ -v`
Expected: all tests PASS, including every pre-existing test in `test_journal_page.py` and
`test_settings_page.py` (proves the markup restructure didn't break any existing selector)

- [ ] **Step 5: Commit**

```bash
git add reconvene/web/static/index.html reconvene/web/static/settings.html reconvene/web/static/style.css tests/e2e/test_journal_page.py tests/e2e/test_settings_page.py
git commit -m "feat: add shared topbar and wrap settings sections in panels"
```

---

### Task 5: Elevation, transitions, and focus polish

**Files:**
- Modify: `reconvene/web/static/style.css`

**Interfaces:**
- Consumes: `.project` (existing), `.panel` (Task 4) — both gain shadow/depth in this task.
- No new selectors; this task only changes CSS property values on existing rules.

This task is pure CSS — no unit-testable logic. Verification is the full existing test suite
(proving no selector broke) plus a manual real-browser check in both light and dark mode.

- [ ] **Step 1: Add the shared accent-glow token**

In `reconvene/web/static/style.css`, in the light `:root` block, add this line after
`--accent-hover: #22903f;`:

```css
  --accent-glow: rgba(26, 127, 55, 0.25);
```

In the dark `@media (prefers-color-scheme: dark) { :root { ... } }` block, add this line after
`--accent-hover: #2ea043;`:

```css
    --accent-glow: rgba(35, 134, 54, 0.25);
```

- [ ] **Step 2: Elevate `.project` cards and replace the brightness-hover hack**

Replace:

```css
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
```

with:

```css
.project {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0.75rem 1rem;
  margin-bottom: 0.5rem;
  cursor: pointer;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
  transition: box-shadow 0.15s ease, transform 0.15s ease;
}

.project:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.45);
  transform: translateY(-2px);
}
```

- [ ] **Step 3: Elevate `.panel`**

Replace:

```css
.panel {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 1rem 1.25rem;
  margin-bottom: 1rem;
}
```

with:

```css
.panel {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 1rem 1.25rem;
  margin-bottom: 1rem;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
}
```

- [ ] **Step 4: Smooth link, button, and input transitions**

Replace:

```css
a {
  color: var(--link);
}
```

with:

```css
a {
  color: var(--link);
}

a:hover {
  text-decoration: underline;
}
```

Replace:

```css
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
```

with:

```css
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
  transition: background-color 0.15s ease, transform 0.1s ease;
}

button:hover {
  background: var(--accent-hover);
  transform: translateY(-1px);
}
```

Replace:

```css
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
```

with:

```css
input[type="text"], select, textarea {
  background: var(--card-bg);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0.4rem 0.6rem;
  font-family: inherit;
  font-size: 0.9rem;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

input[type="text"]:focus, select:focus, textarea:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-glow);
}
```

- [ ] **Step 5: Respect reduced motion for the new hover transforms**

Replace:

```css
@media (prefers-reduced-motion: reduce) {
  .cursor { animation: none; }
}
```

with:

```css
@media (prefers-reduced-motion: reduce) {
  .cursor { animation: none; }
  .project:hover, button:hover { transform: none; }
}
```

- [ ] **Step 6: Run the full existing test suite to confirm nothing broke**

Run: `.venv/bin/python -m pytest tests/ -v`
Expected: all tests PASS (this task changes only CSS property values on existing selectors, so no
test assertion should change)

- [ ] **Step 7: Manually verify in a real browser**

Launch the app against real data (`.venv/bin/reconvene --no-sync`, or a second instance on a free
port if one is already running) and open it in a browser. Confirm, in both light and dark system
appearance:
- Journal cards show a resting shadow and lift on hover.
- Settings panels show the same resting shadow.
- Buttons and inputs transition smoothly on hover/focus instead of snapping.
- With "Reduce motion" enabled (System Settings → Accessibility → Display), cards/buttons no
  longer shift position on hover, but shadow/color changes still occur.

- [ ] **Step 8: Commit**

```bash
git add reconvene/web/static/style.css
git commit -m "feat: add card/panel elevation and interaction transitions"
```
