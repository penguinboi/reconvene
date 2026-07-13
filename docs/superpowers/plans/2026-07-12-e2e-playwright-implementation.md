# Playwright E2E Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Playwright-driven E2E test suite that verifies Reconvene's web UI actually renders and behaves correctly in a real browser — journal page render, async recap fill-in, resume success/failure, and settings view/edit/persist.

**Architecture:** Each test builds its own isolated stack (fresh temp ccrider DB, fresh temp config, a `serve(...)` instance with fake `resumer`/`recap_runner` on a random port, run in a background thread) and drives it with `pytest-playwright`'s `page` fixture. This mirrors the existing HTTP-level test pattern in `tests/test_web_server.py` exactly, just adding a real browser on top instead of raw `urllib` requests.

**Tech Stack:** `playwright` + `pytest-playwright` (test-only dependencies, not runtime deps), Python 3.11+, pytest.

## Global Constraints

- Test-only dependencies — `playwright`/`pytest-playwright` go in `pyproject.toml`'s `[project.optional-dependencies].test`, never in `[project]`'s core deps. The shipped app stays stdlib-only at runtime.
- No security/adversarial testing here (path traversal, malformed input) — that already lives in `tests/test_web_server.py` and stays there.
- No real `claude` CLI or real Terminal-launch automation in these tests — always inject a fake `resumer` and fake `recap_runner`, exactly like the existing HTTP-level tests already do.
- Every server instance must use an explicit `tmp_path`-based `config_path` — never the real default `~/.config/reconvene/config.json` (this project already had one real bug from a test writing to the real filesystem location; do not reintroduce it).

---

## Task 1: Test dependencies, E2E fixture infrastructure, and a smoke test

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/e2e/__init__.py`
- Create: `tests/e2e/conftest.py`
- Create: `tests/e2e/test_smoke.py`
- Modify: `README.md`

**Interfaces:**
- Produces: pytest fixtures `e2e_server` and `e2e_server_failing_resume`, both yielding `(base_url: str, resumed: list[tuple[str, str]], config: Config, config_path: Path)`. Both fixtures depend on the existing `ccrider_db` fixture (from `tests/conftest.py`, automatically available to `tests/e2e/` since it's a subdirectory) and use `add_session`/`add_message` helpers from `tests.conftest` for seeding (imported by later tasks' test files, not this one).

- [ ] **Step 1: Add test dependencies to `pyproject.toml`**

Modify `pyproject.toml` to add an optional dependency group. The file currently reads:

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

Add a `[project.optional-dependencies]` section after `[project.scripts]`:

```toml
[project]
name = "reconvene"
version = "0.1.0"
requires-python = ">=3.11"

[project.scripts]
reconvene = "reconvene.cli:main"

[project.optional-dependencies]
test = ["playwright", "pytest-playwright"]

[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Install the test dependencies and the Chromium browser binary**

Run: `pip install -e ".[test]" && playwright install chromium`
Expected: both commands exit 0. `playwright install chromium` downloads the browser binary (a one-time step per environment, not a pip package).

- [ ] **Step 3: Create `tests/e2e/__init__.py`**

```python
```

- [ ] **Step 4: Create `tests/e2e/conftest.py`**

```python
# ABOUTME: Fixtures starting a real Reconvene server for Playwright-driven E2E tests.
# ABOUTME: Each test gets its own isolated server, temp DB, and temp config — no shared state.
import threading

import pytest

from reconvene.config import Config, save_config
from reconvene.web.server import serve


def _start_server(tmp_path, ccrider_db, resumer):
    config_path = tmp_path / "config.json"
    config = Config()
    save_config(config, config_path)

    def fake_recap_runner(prompt):
        return "ONELINE: full recap text\nDETAIL: full recap text"

    server = serve(
        config, str(ccrider_db), str(tmp_path / "recaps.db"), str(config_path),
        resumer, recap_runner=fake_recap_runner, port=0,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    return server, base_url, config, config_path


@pytest.fixture
def e2e_server(tmp_path, ccrider_db):
    resumed = []

    def fake_resumer(session_id, cwd):
        resumed.append((session_id, cwd))

    server, base_url, config, config_path = _start_server(tmp_path, ccrider_db, fake_resumer)
    yield base_url, resumed, config, config_path
    server.shutdown()
    server.server_close()


@pytest.fixture
def e2e_server_failing_resume(tmp_path, ccrider_db):
    resumed = []

    def failing_resumer(session_id, cwd):
        raise RuntimeError("could not open Terminal")

    server, base_url, config, config_path = _start_server(tmp_path, ccrider_db, failing_resumer)
    yield base_url, resumed, config, config_path
    server.shutdown()
    server.server_close()
```

- [ ] **Step 5: Write the smoke test**

```python
# tests/e2e/test_smoke.py
# ABOUTME: Proves the E2E fixture infrastructure itself works — a real browser can load a
# ABOUTME: page served by a real Reconvene server instance. Substantive flows are in later files.
def test_index_page_loads_in_a_real_browser(page, e2e_server):
    base_url, resumed, config, config_path = e2e_server
    page.goto(base_url)
    assert page.title() == "Reconvene"
```

- [ ] **Step 6: Run the smoke test to verify it passes**

Run: `pytest tests/e2e/test_smoke.py -v`
Expected: PASS (1 test) — a real Chromium instance launches headless, loads the page, and reads its title.

- [ ] **Step 7: Update `README.md`'s testing section**

Add this section to `README.md`, after the existing "Usage" section (before "See `THIRD_PARTY_LICENSES.md`..." if that's the last line, otherwise at the end of the file):

```markdown
## Testing

```bash
pip install -e ".[test]"      # installs pytest-playwright, playwright
playwright install chromium   # one-time browser binary download, not a pip package
pytest tests/                 # runs everything: unit, HTTP-integration, and E2E tests
```

E2E tests (`tests/e2e/`) drive a real browser against a real running server instance, with the
`claude` CLI and Terminal-launch automation always faked — no real subprocess or window is ever
spawned during tests.
```

- [ ] **Step 8: Run the full suite to confirm no regressions**

Run: `pytest tests/ -v`
Expected: all prior tests (47) plus the new smoke test (1) pass — 48 total.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml tests/e2e/__init__.py tests/e2e/conftest.py tests/e2e/test_smoke.py README.md
git commit -m "test: add Playwright E2E test infrastructure and a smoke test"
```

---

## Task 2: Journal page E2E tests

**Files:**
- Create: `tests/e2e/test_journal_page.py`

**Interfaces:**
- Consumes: `e2e_server`, `e2e_server_failing_resume` fixtures from Task 1 (`tests/e2e/conftest.py`); `add_session`, `add_message` from `tests.conftest`.

- [ ] **Step 1: Write the tests**

```python
# tests/e2e/test_journal_page.py
# ABOUTME: E2E tests for the journal page — real render, async recap fill-in, resume success/failure.
# ABOUTME: Verifies what only a real browser can prove: the page actually shows what the API returns.
from tests.conftest import add_session, add_message


def test_journal_renders_project_card(page, e2e_server, ccrider_db):
    base_url, resumed, config, config_path = e2e_server
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "wire up thresholds", sequence=1)

    page.goto(base_url)
    card = page.locator(".project")
    card.wait_for()
    text = card.inner_text()
    assert "myproject" in text
    assert "1 sessions" in text  # app.js doesn't pluralize "sessions" — this is the real rendered text, not a typo


def test_recap_fills_in_asynchronously(page, e2e_server, ccrider_db):
    base_url, resumed, config, config_path = e2e_server
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "wire up thresholds", sequence=1)

    page.goto(base_url)
    meta = page.locator(".project .meta")
    meta.wait_for()
    assert "wire up thresholds" in meta.inner_text()  # fast fallback shows first
    page.wait_for_function(
        "document.querySelector('.project .meta').textContent.includes('full recap text')"
    )


def test_resume_success_dispatches_to_resumer(page, e2e_server, ccrider_db):
    base_url, resumed, config, config_path = e2e_server
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "wire up thresholds", sequence=1)

    page.goto(base_url)
    card = page.locator(".project")
    card.wait_for()
    with page.expect_response(lambda r: "/api/resume/" in r.url) as resp_info:
        card.click()
    response = resp_info.value
    assert response.status == 200
    assert response.json() == {"status": "resumed"}
    assert resumed == [("s1", "/Users/x/Code/myproject")]


def test_resume_failure_shows_inline_error(page, e2e_server_failing_resume, ccrider_db):
    base_url, resumed, config, config_path = e2e_server_failing_resume
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "wire up thresholds", sequence=1)

    page.goto(base_url)
    card = page.locator(".project")
    card.wait_for()
    card.click()
    error = page.locator("#error")
    error.wait_for()
    assert "Couldn't resume" in error.inner_text()
    assert resumed == []
```

- [ ] **Step 2: Run the tests to verify they pass**

Run: `pytest tests/e2e/test_journal_page.py -v`
Expected: PASS (4 tests)

- [ ] **Step 3: Run the full suite to confirm no regressions**

Run: `pytest tests/ -v`
Expected: all 48 prior tests plus these 4 pass — 52 total.

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/test_journal_page.py
git commit -m "test: add E2E tests for journal page render, recap fill-in, and resume flow"
```

---

## Task 3: Settings page E2E tests

**Files:**
- Create: `tests/e2e/test_settings_page.py`

**Interfaces:**
- Consumes: `e2e_server` fixture from Task 1; `add_session`, `add_message` from `tests.conftest`; `load_config` from `reconvene.config`.

- [ ] **Step 1: Write the tests**

```python
# tests/e2e/test_settings_page.py
# ABOUTME: E2E tests for the settings page — shows existing classification overrides correctly,
# ABOUTME: and editing + saving actually round-trips through save_config/load_config on disk.
from reconvene.config import load_config
from tests.conftest import add_session, add_message


def test_settings_shows_existing_classification_override(page, e2e_server, ccrider_db):
    base_url, resumed, config, config_path = e2e_server
    add_session(ccrider_db, "s1", "/Users/x/Code/scoutbot", "2026-07-08 00:00:00", message_count=2)
    add_message(ccrider_db, "s1", "user", "score this idea", sequence=1)
    config.bot_names = {"scoutbot"}  # mutate the same Config instance the running server holds

    page.goto(f"{base_url}/settings.html")
    select = page.locator('select[data-name="scoutbot"]')
    select.wait_for()
    assert select.input_value() == "bot"


def test_settings_edit_and_save_persists_to_disk(page, e2e_server, ccrider_db):
    base_url, resumed, config, config_path = e2e_server
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "wire up thresholds", sequence=1)

    page.goto(f"{base_url}/settings.html")
    select = page.locator('select[data-name="myproject"]')
    select.wait_for()
    select.select_option("drop")
    page.locator('input[name="auth"][value="api_key"]').check()
    page.locator("#apiKey").fill("sk-test-123")

    with page.expect_response(
        lambda r: r.url.endswith("/api/settings") and r.request.method == "POST"
    ) as resp_info:
        page.locator("#save").click()
    assert resp_info.value.status == 200

    reloaded = load_config(config_path)
    assert reloaded.hidden_names == {"myproject"}
    assert reloaded.recap_auth_mode == "api_key"
    assert reloaded.api_key == "sk-test-123"
```

- [ ] **Step 2: Run the tests to verify they pass**

Run: `pytest tests/e2e/test_settings_page.py -v`
Expected: PASS (2 tests)

- [ ] **Step 3: Run the full suite to confirm no regressions**

Run: `pytest tests/ -v`
Expected: all 52 prior tests plus these 2 pass — 54 total.

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/test_settings_page.py
git commit -m "test: add E2E tests for settings page display and persistence round-trip"
```
