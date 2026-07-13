# ABOUTME: Tests for Config load/save round-trip and defaults.
# ABOUTME: Verifies a missing config file yields sensible zero-config defaults.
import json

from reconvene.config import Config, load_config, save_config


def test_load_config_missing_file_returns_defaults(tmp_path):
    config = load_config(tmp_path / "does-not-exist.json")
    assert config.code_root is None
    assert config.bot_names == set()
    assert config.hidden_names == set()
    assert config.hidden_path_substrings == set()
    assert config.recap_auth_mode == "claude_cli"
    assert config.api_key is None


def test_save_then_load_round_trips(tmp_path):
    path = tmp_path / "config.json"
    config = Config(
        code_root="/Users/x/Code",
        bot_names={"scoutbot"},
        hidden_names={"scratch-repo"},
        hidden_path_substrings={"sarb_agent_"},
        recap_auth_mode="api_key",
        api_key="sk-test",
    )
    save_config(config, path)
    loaded = load_config(path)
    assert loaded == config


def test_save_creates_parent_directory(tmp_path):
    path = tmp_path / "nested" / "dir" / "config.json"
    save_config(Config(), path)
    assert path.exists()
    assert json.loads(path.read_text())["recap_auth_mode"] == "claude_cli"
