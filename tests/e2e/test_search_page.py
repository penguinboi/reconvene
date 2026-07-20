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
