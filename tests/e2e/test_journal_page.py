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


def test_journal_escapes_html_in_project_name(page, e2e_server, ccrider_db):
    # A project name is a directory basename from ccrider's DB -- untrusted. It must render as
    # text, never as HTML, or a maliciously-named directory executes arbitrary JS (which can
    # then drive /api/settings and /api/resume).
    base_url, resumed, config, config_path = e2e_server
    add_session(ccrider_db, "s1", "/Users/x/Code/<img src=x onerror=window.__xss=1>",
                "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "hi", sequence=1)

    page.goto(base_url)
    page.locator(".project strong").wait_for()
    assert page.locator(".project img").count() == 0        # payload not parsed as an element
    assert page.evaluate("window.__xss") is None            # onerror never fired
    assert "<img" in page.locator(".project strong").inner_text()  # shown as literal text


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


def _seed_loose_group(ccrider_db):
    # 3 projects under /Users/x/Code make it a root; 2 loose sessions launched from bare /Users/x/Code.
    for sub in ("a", "b", "c"):
        add_session(ccrider_db, f"p{sub}", f"/Users/x/Code/{sub}", "2026-07-01 00:00:00", message_count=10)
        add_message(ccrider_db, f"p{sub}", "user", "work", sequence=1)
    add_session(ccrider_db, "loose_new", "/Users/x/Code", "2026-07-08 00:00:00", message_count=20)
    add_message(ccrider_db, "loose_new", "user", "newer loose", sequence=1)
    add_session(ccrider_db, "loose_old", "/Users/x/Code", "2026-07-02 00:00:00", message_count=30)
    add_message(ccrider_db, "loose_old", "user", "older loose", sequence=1)


def _open_loose_group_modal(page, base_url, ccrider_db):
    _seed_loose_group(ccrider_db)
    page.goto(base_url)
    page.get_by_text("loose sessions").click()
    page.locator(".session-row").first.wait_for()


def _background_of(page, selector):
    return page.evaluate(
        f"getComputedStyle(document.querySelector({selector!r})).backgroundColor"
    )


def test_loose_group_preselects_its_latest_session(page, e2e_server, ccrider_db):
    base_url, resumed, _, _ = e2e_server
    _open_loose_group_modal(page, base_url, ccrider_db)

    resume = page.locator("#modalConfirm")
    assert not resume.is_disabled()
    selected = page.locator(".session-row.selected")
    assert selected.count() == 1
    assert "newer loose" in selected.inner_text()

    resume.click()
    page.wait_for_timeout(300)
    assert [r[0] for r in resumed] == ["loose_new"]


def test_loose_group_lets_the_user_override_the_preselected_session(page, e2e_server, ccrider_db):
    base_url, resumed, _, _ = e2e_server
    _open_loose_group_modal(page, base_url, ccrider_db)

    page.locator(".session-row", has_text="older loose").click()
    assert page.locator(".session-row.selected").count() == 1  # selection moves, never accumulates
    page.locator("#modalConfirm").click()
    page.wait_for_timeout(300)
    assert [r[0] for r in resumed] == ["loose_old"]


def test_session_picker_tells_the_user_the_rows_are_choices(page, e2e_server, ccrider_db):
    # Without a label the rows read as metadata, so nobody discovers they can pick a different one.
    base_url, _, _, _ = e2e_server
    _open_loose_group_modal(page, base_url, ccrider_db)

    assert "Pick a session" in page.locator(".session-hint").inner_text()


def test_selected_session_row_is_visible_against_the_modal(page, e2e_server, ccrider_db):
    # A preselected session the user cannot see is worse than none -- they would resume blind.
    # The selected background must differ from the modal's own, not just carry a 1px border.
    base_url, _, _, _ = e2e_server
    _open_loose_group_modal(page, base_url, ccrider_db)

    assert _background_of(page, ".session-row.selected") != _background_of(page, ".modal-content")


def test_hovering_a_session_row_is_visible_against_the_modal(page, e2e_server, ccrider_db):
    # Hover is the only cue that these rows are clickable. Painting them the modal's own
    # background makes that cue a no-op, which is how the picker went unnoticed.
    base_url, _, _, _ = e2e_server
    _open_loose_group_modal(page, base_url, ccrider_db)

    row = page.locator(".session-row", has_text="older loose")  # unselected, so hover is the only change
    row.hover()
    assert _background_of(page, ".session-row:hover") != _background_of(page, ".modal-content")


def test_search_result_modal_shows_session_recap(page, e2e_server, ccrider_db):
    base_url, _, _, _ = e2e_server
    add_session(ccrider_db, "nas1", "/Users/x/Code/homelab", "2026-07-07 00:00:00", message_count=30)
    add_message(ccrider_db, "nas1", "user", "tune the synology nas raid", sequence=1)
    page.goto(base_url)
    page.fill("#searchBox", "synology")
    page.locator(".search-hit").first.click()
    # The fake recap runner returns "full recap text" as the DETAIL body.
    page.get_by_text("full recap text").wait_for()


def test_page_has_penguinboi_brand(page, e2e_server, ccrider_db):
    base_url, _, _, _ = e2e_server
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "hi", sequence=1)
    page.goto(base_url)
    # Topbar penguin logo
    logo = page.locator("img.topbar-logo")
    assert logo.count() == 1
    assert "penguin-mascot" in logo.get_attribute("src")  # the waving-penguin mascot, not the favicon
    # The browser-tab favicon is still the penguin+d20 icon
    assert page.locator("head link[rel='icon'][href*='favicon']").count() >= 1
    # Footer attribution linking to penguinboisoftware.com
    footer_link = page.locator(".site-footer a[href='https://penguinboisoftware.com']")
    assert footer_link.count() == 1
    assert "Penguinboi Software" in footer_link.inner_text()
    # Favicon is actually served
    resp = page.request.get(f"{base_url}/favicon.png")
    assert resp.status == 200


# --- agent badges, "Open in" switch, handoff -----------------------------------------------

def _seed_mixed_agents(ccrider_db):
    add_session(ccrider_db, "claude_old", "/Users/x/Code/mixed", "2026-07-08 00:00:00",
                message_count=4, provider="claude")
    add_message(ccrider_db, "claude_old", "user", "older claude work", sequence=1)
    add_session(ccrider_db, "codex_new", "/Users/x/Code/mixed", "2026-07-09 00:00:00",
                message_count=4, provider="codex")
    add_message(ccrider_db, "codex_new", "user", "newer codex work", sequence=1)


def _open_mixed_modal(page, base_url, ccrider_db):
    _seed_mixed_agents(ccrider_db)
    page.goto(base_url)
    page.locator(".project").click()
    page.locator(".session-row").first.wait_for()


def test_session_rows_show_agent_badges(page, e2e_server_with_handoff, ccrider_db):
    base_url, _, _, _ = e2e_server_with_handoff
    _open_mixed_modal(page, base_url, ccrider_db)

    assert page.locator(".session-row", has_text="newer codex").locator(".agent-badge.agent-codex").count() == 1
    assert page.locator(".session-row", has_text="older claude").locator(".agent-badge.agent-claude").count() == 1


def test_open_in_switch_follows_selected_session(page, e2e_server_with_handoff, ccrider_db):
    base_url, _, _, _ = e2e_server_with_handoff
    _open_mixed_modal(page, base_url, ccrider_db)

    assert page.locator("#modalConfirm").inner_text() == "Resume in Codex"
    assert page.locator('#modalAgentSwitch button[data-agent="codex"]').get_attribute("class") == "selected"
    page.locator(".session-row", has_text="older claude").click()
    assert page.locator("#modalConfirm").inner_text() == "Resume in Claude"
    assert page.locator('#modalAgentSwitch button.selected').get_attribute("data-agent") == "claude"


def test_open_in_switch_shows_for_single_session_project(page, e2e_server_with_handoff, ccrider_db):
    base_url, _, _, _ = e2e_server_with_handoff
    add_session(ccrider_db, "solo", "/Users/x/Code/solo", "2026-07-09 00:00:00", provider="codex")
    add_message(ccrider_db, "solo", "user", "only one", sequence=1)
    page.goto(base_url)
    page.locator(".project").click()

    page.locator("#modalAgentSwitch button").first.wait_for()
    assert page.locator("#modalConfirm").inner_text() == "Resume in Codex"
    assert page.locator("#modalAgentSwitch button").count() == 3


def test_switching_agent_changes_button_to_hand_off(page, e2e_server_with_handoff, ccrider_db):
    base_url, _, _, _ = e2e_server_with_handoff
    _open_mixed_modal(page, base_url, ccrider_db)

    page.locator('#modalAgentSwitch button[data-agent="claude"]').click()
    assert page.locator("#modalConfirm").inner_text() == "Hand off to Claude"
    page.locator('#modalAgentSwitch button[data-agent="codex"]').click()
    assert page.locator("#modalConfirm").inner_text() == "Resume in Codex"


def test_uninstalled_agent_is_disabled(page, e2e_server_with_handoff, ccrider_db):
    base_url, _, _, _ = e2e_server_with_handoff
    _open_mixed_modal(page, base_url, ccrider_db)

    assert page.locator('#modalAgentSwitch button[data-agent="antigravity"]').is_disabled()
    assert not page.locator('#modalAgentSwitch button[data-agent="claude"]').is_disabled()


def test_hand_off_posts_target_agent(page, e2e_server_with_handoff, ccrider_db):
    base_url, resumed, handoffs, _ = e2e_server_with_handoff
    _open_mixed_modal(page, base_url, ccrider_db)

    page.locator('#modalAgentSwitch button[data-agent="claude"]').click()
    page.locator("#modalConfirm").click()
    page.locator("#confirmModal.hidden").wait_for(state="attached")
    assert handoffs == [("codex_new", "claude")]
    assert resumed == []


def test_native_resume_still_closes_modal_and_resumes(page, e2e_server_with_handoff, ccrider_db):
    base_url, resumed, handoffs, _ = e2e_server_with_handoff
    _open_mixed_modal(page, base_url, ccrider_db)

    page.locator("#modalConfirm").click()
    page.wait_for_timeout(300)
    assert resumed == ["codex_new"]
    assert handoffs == []


def test_handoff_button_disabled_while_working(page, e2e_server_with_handoff, ccrider_db):
    base_url, _, handoffs, hold = e2e_server_with_handoff
    hold["release"] = threading.Event()
    _open_mixed_modal(page, base_url, ccrider_db)

    page.locator('#modalAgentSwitch button[data-agent="claude"]').click()
    button = page.locator("#modalConfirm")
    button.click()
    page.locator("#modalConfirm", has_text="Summarizing with Claude…").wait_for()
    assert button.is_disabled()
    assert page.locator("#confirmModal.hidden").count() == 0  # modal stays open during the handoff
    button.click(force=True)
    page.wait_for_timeout(200)
    assert len(handoffs) == 1

    hold["release"].set()
    page.locator("#confirmModal.hidden").wait_for(state="attached")
    assert len(handoffs) == 1


def test_handoff_error_shows_in_modal_and_reenables(page, e2e_server_with_handoff, ccrider_db):
    base_url, _, handoffs, hold = e2e_server_with_handoff
    hold["error"] = "summary failed"
    _open_mixed_modal(page, base_url, ccrider_db)

    page.locator('#modalAgentSwitch button[data-agent="claude"]').click()
    page.locator("#modalConfirm").click()
    error = page.locator("#modalError")
    error.wait_for(state="visible")
    assert "summary failed" in error.inner_text()
    assert page.locator("#confirmModal.hidden").count() == 0
    assert not page.locator("#modalConfirm").is_disabled()
    assert page.locator("#modalConfirm").inner_text() == "Hand off to Claude"


def test_selected_agent_button_is_visible_against_switch(page, e2e_server_with_handoff, ccrider_db):
    # Guards the token-collision class in CLAUDE.md: the selected button must not share a
    # background with its container or with an unselected sibling.
    base_url, _, _, _ = e2e_server_with_handoff
    _open_mixed_modal(page, base_url, ccrider_db)

    selected = _background_of(page, "#modalAgentSwitch button.selected")
    assert selected != _background_of(page, "#modalAgentSwitch")
    assert selected != _background_of(page, "#modalAgentSwitch button:not(.selected):not(:disabled)")


def test_handoff_in_flight_locks_switch_and_rows(page, e2e_server_with_handoff, ccrider_db):
    base_url, _, handoffs, hold = e2e_server_with_handoff
    hold["release"] = threading.Event()
    hold["error"] = "summary failed"
    _open_mixed_modal(page, base_url, ccrider_db)

    page.locator('#modalAgentSwitch button[data-agent="claude"]').click()
    page.locator("#modalConfirm").click()
    page.locator("#modalConfirm", has_text="Summarizing with Claude…").wait_for()

    page.locator('#modalAgentSwitch button[data-agent="codex"]').click(force=True)
    page.locator(".session-row", has_text="older claude").click()
    assert page.locator("#modalConfirm").inner_text() == "Summarizing with Claude…"
    assert page.evaluate("document.getElementById('confirmModal').dataset.agent") == "claude"
    assert "newer codex" in page.locator(".session-row.selected").inner_text()

    hold["release"].set()
    page.locator("#modalError").wait_for(state="visible")
    assert page.locator("#modalConfirm").inner_text() == "Hand off to Claude"
    assert page.locator('#modalAgentSwitch button.selected').get_attribute("data-agent") == "claude"
    assert not page.locator('#modalAgentSwitch button[data-agent="codex"]').is_disabled()


def test_handoff_non_json_failure_shows_error_and_reenables(page, e2e_server_with_handoff, ccrider_db):
    base_url, _, _, _ = e2e_server_with_handoff
    page.route("**/api/resume/*", lambda route: route.fulfill(
        status=500, content_type="text/html", body="<html>proxy exploded</html>"))
    _open_mixed_modal(page, base_url, ccrider_db)

    page.locator('#modalAgentSwitch button[data-agent="claude"]').click()
    page.locator("#modalConfirm").click()
    error = page.locator("#modalError")
    error.wait_for(state="visible")
    assert error.inner_text().strip() != ""
    assert not page.locator("#modalConfirm").is_disabled()
    assert page.locator("#modalConfirm").inner_text() == "Hand off to Claude"


def test_agents_fetch_failure_is_shown(page, e2e_server_with_handoff, ccrider_db):
    base_url, _, _, _ = e2e_server_with_handoff
    page.route("**/api/agents", lambda route: route.abort())
    _seed_mixed_agents(ccrider_db)
    page.goto(base_url)
    page.locator(".project").click()
    page.locator("#error").wait_for(state="visible")
    assert "agent list" in page.locator("#error").inner_text().lower()


def test_agents_fetch_is_retried_after_a_failure(page, e2e_server_with_handoff, ccrider_db):
    base_url, _, _, _ = e2e_server_with_handoff
    page.route("**/api/agents", lambda route: route.abort())
    _seed_mixed_agents(ccrider_db)
    page.goto(base_url)
    page.locator(".project").click()
    page.locator("#error").wait_for(state="visible")
    page.unroute("**/api/agents")
    page.locator("#modalCancel").click()
    page.locator(".project").click()
    page.locator('#modalAgentSwitch button[data-agent="codex"]').wait_for()


def test_cancel_is_disabled_while_handoff_is_in_flight(page, e2e_server_with_handoff, ccrider_db):
    base_url, _, handoffs, hold = e2e_server_with_handoff
    hold["release"] = threading.Event()
    _open_mixed_modal(page, base_url, ccrider_db)

    page.locator('#modalAgentSwitch button[data-agent="claude"]').click()
    page.locator("#modalConfirm").click()
    page.locator("#modalConfirm", has_text="Summarizing with Claude…").wait_for()
    cancel = page.locator("#modalCancel")
    assert cancel.is_disabled()
    cancel.click(force=True)
    page.wait_for_timeout(200)
    assert page.locator("#confirmModal.hidden").count() == 0
    assert len(handoffs) == 1

    hold["release"].set()
    page.locator("#confirmModal.hidden").wait_for(state="attached")
    page.locator(".project").click()
    assert not page.locator("#modalCancel").is_disabled()
    page.locator("#modalCancel").click()
    page.locator("#confirmModal.hidden").wait_for(state="attached")
