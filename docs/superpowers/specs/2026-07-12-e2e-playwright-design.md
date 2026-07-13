# Playwright E2E Tests — Design

## What it is

An end-to-end test suite that drives Reconvene's actual web UI in a real browser (via
Playwright), covering the user-facing flows that the existing HTTP-level tests
(`tests/test_web_server.py`, `tests/test_e2e.py`) exercise at the request/response level but
never verify render correctly or behave correctly from a real page load and real user
interaction.

This is additive, not a replacement: the existing pytest suite (unit tests per module, HTTP
integration tests against a running server) is unchanged and continues to cover things a browser
test shouldn't duplicate — schema validation, classification logic, path-traversal security,
JSON contract shapes. The Playwright suite covers what only a real browser can prove: does the
page actually render what the API returns, does the async recap fill-in visibly happen, does a
click actually trigger the right network call, does the settings form actually round-trip.

## Non-goals

- Not a replacement for any existing test. Nothing in `tests/test_web_server.py` or
  `tests/test_e2e.py` is removed or superseded.
- Not testing security/adversarial paths (path traversal, malformed input) — that stays at the
  HTTP level where it already lives and is more precise to assert on.
- Not testing the actual `claude` CLI or real Terminal-launch automation (`open_terminal_and_resume`)
  — those remain covered by injected fakes, same as the rest of the suite. Browser E2E tests
  verify the *page's* behavior, not the OS-level side effects a real resume triggers.

## Dependencies

`playwright` and `pytest-playwright`, added as test-only dependencies — declared in
`pyproject.toml` under `[project.optional-dependencies]` (`test = ["playwright", "pytest-playwright"]`),
not in `[project]`'s core dependencies (there are none today; this preserves that for the actual
package). Installing the test extras additionally requires a one-time
`playwright install chromium` step (downloads the browser binary; not a pip package, documented
in the README's testing section).

## Architecture

Each E2E test constructs its own isolated stack, mirroring the pattern `tests/test_web_server.py`
already uses:

1. A fresh temp `ccrider_db` (via the existing `conftest.py` fixture) seeded with `add_session`/`add_message`.
2. A fresh `Config` and a fresh temp `config_path` (`tmp_path`-based, never the real
   `~/.config/reconvene/config.json` — same discipline as the rest of the suite, given the real
   bug already found and fixed here once).
3. `serve(...)` started on `port=0` with a fake `resumer` and fake `recap_runner` (same signature
   as the existing HTTP-level tests), running in a background thread.
4. A Playwright `page` (from `pytest-playwright`'s function-scoped fixture, backed by a
   session-scoped `browser` fixture — so the browser process itself only launches once per test
   run, not once per test) navigates to the server's real `http://127.0.0.1:<port>/` URL.

A new pytest fixture, `e2e_server` (in `tests/e2e/conftest.py`), packages steps 1-3 into one
reusable fixture returning `(base_url, resumed_calls, config_path)` — the same shape of
information the existing `running_server` fixture in `tests/test_web_server.py` already exposes,
so the two test styles stay consistent.

## Test Plan

`tests/e2e/test_journal_page.py`:
- Loads `/`, waits for at least one project card, asserts the project name and session count
  render (values that only exist if `/api/journal`'s response was actually fetched and rendered
  into the DOM — not just that the endpoint returns correct JSON, which is already covered).
- Asserts a card's text visibly changes from the fast fallback text to the fake `recap_runner`'s
  full response — proving the async fill-in actually happens in a real page, not just that the
  `/api/recap/<name>` endpoint returns the right JSON in isolation.
- Clicks a project card, intercepts the resulting `POST /api/resume/<id>` network response via
  Playwright's request/response listening, and asserts both the response body (`{"status":
  "resumed"}`) and that the fake resumer recorded the correct `(session_id, project_path)` pair.
- Repeats the click with a failing fake resumer and asserts the inline `.error` banner becomes
  visible with the expected message — proving the error path the app.js code added specifically
  to avoid silent failures actually surfaces in the real page.

`tests/e2e/test_settings_page.py`:
- Loads `/settings.html` with a config that already has a classification override, asserts the
  correct dropdown option is pre-selected for that project.
- Changes a project's classification dropdown and the recap auth-mode radio, clicks Save,
  reloads the page, and asserts the change persisted — proving the real round-trip through
  `save_config`/`load_config` at the given `config_path`, not just that the POST handler updates
  the in-memory `Config` object (already covered at the HTTP level, but not through a real
  save-then-reload cycle via the browser).

## Testing the Tests

Since this whole suite is new test infrastructure, its own "test" is: does it fail when it
should? Each test's design above already includes at least one assertion that would only pass if
the real browser-rendered behavior is correct (not just the API), which is the point — but per
this project's TDD discipline, each test will still be written and confirmed to fail first
(e.g., against a deliberately broken selector or an unimplemented assertion) before the
implementation task marks it passing, same as every other task in this project.

## CI / Local Dev Note

`playwright install chromium` must run once per environment before these tests can execute
(documented in README.md's testing section, added by this work). This is the only step in the
whole project that requires downloading a binary asset outside of pip — worth calling out
explicitly since it's a first for this stdlib-only-at-runtime project.
