# ABOUTME: Tests for session-path classification (drop/bot/real) and canonical project naming.
# ABOUTME: Verifies worktree/case folding, config-driven overrides, and heuristic promote/drop rules.
from reconvene.classify import canonical_name, classify_category
from reconvene.config import Config


def test_canonical_folds_worktree_and_case():
    assert canonical_name("/Users/x/Code/acme/myproject") == "myproject"
    assert canonical_name("/Users/x/Code/myproject") == "myproject"
    assert canonical_name("/Users/x/Code/acme/myproject/.claude-worktrees/h2") == "myproject"
    assert canonical_name("/Users/x/Code/myorg/WidgetApp") == "widgetapp"


def test_classify_drops_scratch_paths():
    config = Config()
    assert classify_category("/private/tmp/claude-503/x/scratchpad", config) == "drop"


def test_classify_real_by_default_with_no_code_root():
    # zero-config: no code_root set, project is real unless config says otherwise
    config = Config()
    assert classify_category("/Users/x/Code/myproject", config, message_count=10) == "real"


def test_classify_respects_code_root_when_set():
    config = Config(code_root="/Users/x/Code")
    assert classify_category("/Users/x/Downloads/thing", config, message_count=10) == "drop"
    assert classify_category("/Users/x/Code/myproject", config, message_count=10) == "real"


def test_classify_respects_code_root_with_trailing_slash():
    config = Config(code_root="/Users/x/Code/")
    assert classify_category("/Users/x/Downloads/thing", config, message_count=10) == "drop"
    assert classify_category("/Users/x/Code/myproject", config, message_count=10) == "real"


def test_classify_bot_names_override():
    config = Config(bot_names={"scoutbot"})
    assert classify_category("/Users/x/Code/scoutbot", config, message_count=2) == "bot"


def test_classify_hidden_names_override():
    config = Config(hidden_names={"scratch-repo"})
    assert classify_category("/Users/x/Code/scratch-repo", config, message_count=10) == "drop"


def test_classify_hidden_path_substrings_drops_matching_paths():
    config = Config(hidden_path_substrings={"sarb_agent_"})
    assert classify_category("/Users/x/Code/sarb_agent_b7tzmkgv", config, message_count=40) == "drop"
    assert classify_category("/Users/x/Code/myproject", config, message_count=40) == "real"


def test_classify_promotes_long_bot_sessions_to_real():
    config = Config(bot_names={"scoutbot"})
    assert classify_category("/Users/x/Code/scoutbot", config, message_count=2) == "bot"
    assert classify_category("/Users/x/Code/scoutbot", config, message_count=31) == "real"


def test_classify_drops_trivial_real_sessions():
    config = Config()
    assert classify_category("/Users/x/Code/anything", config, message_count=2) == "drop"
    assert classify_category("/Users/x/Code/anything", config, message_count=3) == "real"
