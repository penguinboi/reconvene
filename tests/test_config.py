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
    assert config.terminal_app == "Terminal"
    assert config.claude_extra_args == ""


def test_save_then_load_round_trips(tmp_path):
    path = tmp_path / "config.json"
    config = Config(
        code_root="/Users/x/Code",
        bot_names={"scoutbot"},
        hidden_names={"scratch-repo"},
        hidden_path_substrings={"sarb_agent_"},
        recap_auth_mode="api_key",
        api_key="sk-test",
        terminal_app="iTerm2",
        claude_extra_args="--dangerously-skip-permissions",
    )
    save_config(config, path)
    loaded = load_config(path)
    assert loaded == config


def test_save_creates_parent_directory(tmp_path):
    path = tmp_path / "nested" / "dir" / "config.json"
    save_config(Config(), path)
    assert path.exists()
    assert json.loads(path.read_text())["recap_auth_mode"] == "claude_cli"


def test_config_round_trips_agent_extra_args(tmp_path):
    path = tmp_path / "config.json"
    save_config(Config(codex_extra_args="--full-auto", antigravity_extra_args="--yolo"), path)
    loaded = load_config(path)
    assert loaded.codex_extra_args == "--full-auto"
    assert loaded.antigravity_extra_args == "--yolo"


def test_config_without_agent_extra_args_keys_defaults_to_empty():
    config = Config.from_dict({"terminal_app": "iTerm2"})
    assert config.codex_extra_args == ""
    assert config.antigravity_extra_args == ""
