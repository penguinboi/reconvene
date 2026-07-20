# ABOUTME: E2E for the light/dark/auto theme toggle — cycle, computed-color override, reload persistence.
# ABOUTME: Uses the shared e2e_server fixture; asserts real rendered background colors, not just attrs.
from tests.conftest import add_session, add_message


def _seed(db):
    add_session(db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(db, "s1", "user", "hi", sequence=1)


def _bg(page):
    return page.eval_on_selector("body", "el => getComputedStyle(el).backgroundColor")


def test_theme_toggle_cycles_auto_light_dark(page, e2e_server, ccrider_db):
    base_url, _, _, _ = e2e_server
    _seed(ccrider_db)
    page.goto(base_url)
    root = page.locator("html")
    btn = page.locator("#themeToggle")
    assert btn.count() == 1
    assert root.get_attribute("data-theme") is None            # auto: no attribute

    btn.click()                                                # → light
    assert root.get_attribute("data-theme") == "light"
    assert "☀" in btn.inner_text()
    assert page.evaluate("localStorage.getItem('reconvene-theme')") == "light"
    assert _bg(page) == "rgb(255, 255, 255)"                   # light --bg #ffffff

    btn.click()                                                # → dark
    assert root.get_attribute("data-theme") == "dark"
    assert "🌙" in btn.inner_text()
    assert _bg(page) == "rgb(13, 17, 23)"                      # dark --bg #0d1117 (overrides light system)

    btn.click()                                                # → auto
    assert root.get_attribute("data-theme") is None
    assert page.evaluate("localStorage.getItem('reconvene-theme')") == "auto"


def test_theme_persists_across_reload_pre_paint(page, e2e_server, ccrider_db):
    base_url, _, _, _ = e2e_server
    _seed(ccrider_db)
    page.goto(base_url)
    page.locator("#themeToggle").click()                       # choose light
    page.locator("#themeToggle").click()                       # choose dark
    assert page.locator("html").get_attribute("data-theme") == "dark"

    page.reload()
    # The inline <head> script reapplied data-theme before paint, so the body renders dark.
    assert page.locator("html").get_attribute("data-theme") == "dark"
    assert _bg(page) == "rgb(13, 17, 23)"


def test_no_stored_pref_stays_auto(page, e2e_server, ccrider_db):
    base_url, _, _, _ = e2e_server
    _seed(ccrider_db)
    page.goto(base_url)
    assert page.locator("html").get_attribute("data-theme") is None
