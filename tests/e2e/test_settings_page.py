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
    page.locator("#hiddenPathSubstrings").fill("sarb_agent_\nscratch-")
    page.locator("#terminalApp").select_option("iTerm2")
    page.locator("#claudeExtraArgs").fill("--dangerously-skip-permissions")

    with page.expect_response(
        lambda r: r.url.endswith("/api/settings") and r.request.method == "POST"
    ) as resp_info:
        page.locator("#save").click()
    assert resp_info.value.status == 200

    reloaded = load_config(config_path)
    assert reloaded.hidden_names == {"myproject"}
    assert reloaded.recap_auth_mode == "api_key"
    assert reloaded.api_key == "sk-test-123"
    assert reloaded.hidden_path_substrings == {"sarb_agent_", "scratch-"}
    assert reloaded.terminal_app == "iTerm2"
    assert reloaded.claude_extra_args == "--dangerously-skip-permissions"
