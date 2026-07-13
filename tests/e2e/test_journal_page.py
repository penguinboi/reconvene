# ABOUTME: E2E tests for the journal page — real render, async recap fill-in, resume success/failure.
# ABOUTME: Verifies what only a real browser can prove: the page actually shows what the API returns.
import time

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

    def delay_recap_response(route):
        time.sleep(0.1)
        route.continue_()

    page.route("**/api/recap/**", delay_recap_response)

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
