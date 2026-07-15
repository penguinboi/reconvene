# ABOUTME: E2E tests for the journal page — real render, async recap fill-in, resume success/failure.
# ABOUTME: Verifies what only a real browser can prove: the page actually shows what the API returns.
import threading
import time
from datetime import datetime, timedelta

from reconvene.config import Config, save_config
from reconvene.web.server import serve
from tests.conftest import add_session, add_message


def _start_server_with_recap_runner(tmp_path, ccrider_db, recap_runner):
    # A test-local server (not the shared e2e_server fixture) so a slow recap_runner can delay a
    # response without touching the shared fixture other tests depend on. The delay runs on the
    # *server's* own thread pool -- a separate process from Playwright's driver -- so it never
    # blocks Playwright's own commands the way a time.sleep() inside a page.route() handler would
    # (that blocks the whole sync driver thread; nothing else, not even .wait_for()/.click(),
    # can run until it returns).
    config_path = tmp_path / "config.json"
    config = Config()
    save_config(config, config_path)
    server = serve(
        config, str(ccrider_db), str(tmp_path / "recaps.db"), str(config_path),
        lambda sid, cwd: None, recap_runner=recap_runner, port=0,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    return server, base_url


def _slow_recap_runner(prompt):
    time.sleep(0.3)
    return "ONELINE: full recap text\nDETAIL: full recap text"


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
    assert page.locator("h1 .cursor").count() == 1


def test_topbar_home_link_and_settings_nav_present(page, e2e_server):
    base_url, resumed, config, config_path = e2e_server
    page.goto(base_url)
    page.locator(".topbar").wait_for()
    assert page.locator(".topbar-home").get_attribute("href") == "/"
    assert page.locator(".topbar a", has_text="Settings").get_attribute("href") == "/settings.html"


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


def test_recap_fills_in_asynchronously(page, tmp_path, ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "wire up thresholds", sequence=1)

    server, base_url = _start_server_with_recap_runner(tmp_path, ccrider_db, _slow_recap_runner)
    try:
        page.goto(base_url)
        meta = page.locator(".project .meta")
        meta.wait_for()
        assert "wire up thresholds" in meta.inner_text()  # fast fallback shows first
        page.wait_for_function(
            "document.querySelector('.project .meta').textContent.includes('full recap text')"
        )
    finally:
        server.shutdown()
        server.server_close()


def test_clicking_card_shows_confirm_modal_with_full_recap(page, e2e_server, ccrider_db):
    base_url, resumed, config, config_path = e2e_server
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "wire up thresholds", sequence=1)

    page.goto(base_url)
    card = page.locator(".project")
    card.wait_for()
    page.wait_for_function(
        "document.querySelector('.project .meta').textContent.includes('full recap text')"
    )
    card.click()
    modal = page.locator("#confirmModal")
    modal.wait_for()
    assert "myproject" in page.locator("#modalProjectName").inner_text()
    assert "full recap text" in page.locator("#modalFullRecap").inner_text()
    assert resumed == []  # clicking the card alone must not resume anything yet


def test_modal_shows_loading_placeholder_then_updates_when_recap_arrives(page, tmp_path, ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "wire up thresholds", sequence=1)

    server, base_url = _start_server_with_recap_runner(tmp_path, ccrider_db, _slow_recap_runner)
    try:
        page.goto(base_url)
        meta = page.locator(".project .meta")
        meta.wait_for()
        assert "wire up thresholds" in meta.inner_text()  # confirms we're still in the pre-recap window
        page.locator(".project").click()
        modal_text = page.locator("#modalFullRecap")
        modal_text.wait_for()
        assert modal_text.inner_text() == "Loading full summary…"
        page.wait_for_function(
            "document.getElementById('modalFullRecap').textContent.includes('full recap text')"
        )
    finally:
        server.shutdown()
        server.server_close()


def test_clicking_card_alone_does_not_resume(page, e2e_server, ccrider_db):
    base_url, resumed, config, config_path = e2e_server
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "wire up thresholds", sequence=1)

    page.goto(base_url)
    card = page.locator(".project")
    card.wait_for()
    card.click()
    page.locator("#confirmModal").wait_for()
    page.wait_for_timeout(200)  # give any accidental immediate POST a chance to have fired
    assert resumed == []


def test_confirm_dispatches_resume(page, e2e_server, ccrider_db):
    base_url, resumed, config, config_path = e2e_server
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "wire up thresholds", sequence=1)

    page.goto(base_url)
    card = page.locator(".project")
    card.wait_for()
    card.click()
    page.locator("#confirmModal").wait_for()
    with page.expect_response(lambda r: "/api/resume/" in r.url) as resp_info:
        page.locator("#modalConfirm").click()
    response = resp_info.value
    assert response.status == 200
    assert response.json() == {"status": "resumed"}
    assert resumed == [("s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00")]
    assert page.locator("#confirmModal").is_hidden()


def test_cancel_does_not_resume(page, e2e_server, ccrider_db):
    base_url, resumed, config, config_path = e2e_server
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "wire up thresholds", sequence=1)

    page.goto(base_url)
    card = page.locator(".project")
    card.wait_for()
    card.click()
    page.locator("#confirmModal").wait_for()
    page.locator("#modalCancel").click()
    assert page.locator("#confirmModal").is_hidden()
    assert resumed == []


def test_resume_failure_shows_inline_error(page, e2e_server_failing_resume, ccrider_db):
    base_url, resumed, config, config_path = e2e_server_failing_resume
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "wire up thresholds", sequence=1)

    page.goto(base_url)
    card = page.locator(".project")
    card.wait_for()
    card.click()
    page.locator("#confirmModal").wait_for()
    page.locator("#modalConfirm").click()
    error = page.locator("#error")
    error.wait_for()
    assert "Couldn't resume" in error.inner_text()
    assert resumed == []
