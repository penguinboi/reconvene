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
        time.sleep(0.1)  # guarantees the fast fallback text is observable before the recap replaces it
        route.continue_()

    page.route("**/api/recap/**", delay_recap_response)

    page.goto(base_url)
    meta = page.locator(".project .meta")
    meta.wait_for()
    assert "wire up thresholds" in meta.inner_text()  # fast fallback shows first
    page.wait_for_function(
        "document.querySelector('.project .meta').textContent.includes('full recap text')"
    )


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
    assert resumed == [("s1", "/Users/x/Code/myproject")]
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
