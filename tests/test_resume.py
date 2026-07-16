# ABOUTME: Tests for building the resume command and the macOS terminal-launch automation.
# ABOUTME: Injects a fake subprocess runner so no real Terminal window is ever opened in tests.
from datetime import datetime

import pytest

from reconvene.config import Config
from reconvene.resume import (
    _applescript_escape,
    open_terminal_and_resume,
    resume_command,
    resume_prompt,
)

UPDATED_AT = "2026-07-15 10:00:00"
NOW = datetime(2026, 7, 15, 10, 6, 0)


def test_resume_command():
    assert resume_command("abc123", UPDATED_AT, now=NOW) == [
        "claude", "--resume", "abc123", resume_prompt(UPDATED_AT, NOW),
    ]


def test_resume_command_appends_extra_args():
    assert resume_command("abc123", UPDATED_AT, extra_args="--dangerously-skip-permissions", now=NOW) == [
        "claude", "--resume", "abc123", "--dangerously-skip-permissions",
        resume_prompt(UPDATED_AT, NOW),
    ]


def test_resume_prompt_format():
    prompt = resume_prompt(UPDATED_AT, NOW)
    assert prompt == (
        "Resuming session from 2026-07-15 10:00:00.\n\n"
        "IMPORTANT: This session has been inactive for 6 minutes ago. Before proceeding: "
        "check git status, look around to understand what changed, "
        "and be careful not to overwrite any work in progress."
    )


def test_resume_prompt_truncates_real_ccrider_timestamp_format():
    now = datetime(2026, 7, 13, 10, 12, 20)
    prompt = resume_prompt("2026-07-13 10:12:17.839 +0000 UTC", now)
    assert prompt.startswith("Resuming session from 2026-07-13 10:12:17.\n\n")
    assert "just now" in prompt


def test_open_terminal_and_resume_runs_osascript():
    captured = {}
    def fake_runner(cmd, check):
        captured["cmd"] = cmd
        captured["check"] = check
    open_terminal_and_resume("abc123", "/Users/x/Code/myproject", UPDATED_AT, runner=fake_runner,
                             path_exists=lambda p: True)
    assert captured["cmd"][0] == "osascript"
    assert captured["cmd"][1] == "-e"
    script = captured["cmd"][2]
    assert "Terminal" in script
    assert "activate" in script  # brings the new window to the foreground, not just spawns it silently
    assert "/Users/x/Code/myproject" in script
    assert "claude --resume abc123" in script
    assert "Resuming session from" in script  # the injected reminder is present in the typed command
    assert captured["check"] is True


def test_open_terminal_and_resume_raises_on_failure():
    def failing_runner(cmd, check):
        raise RuntimeError("osascript not found")
    with pytest.raises(RuntimeError, match="osascript not found"):
        open_terminal_and_resume("abc123", "/Users/x/Code/myproject", UPDATED_AT, runner=failing_runner,
                                 path_exists=lambda p: True)


def test_open_terminal_and_resume_uses_iterm2_when_configured():
    captured = {}
    def fake_runner(cmd, check):
        captured["cmd"] = cmd
    config = Config(terminal_app="iTerm2")
    open_terminal_and_resume("abc123", "/Users/x/Code/myproject", UPDATED_AT, config=config, runner=fake_runner,
                             path_exists=lambda p: True)
    script = captured["cmd"][2]
    assert "iTerm2" in script
    assert "activate" in script
    assert "/Users/x/Code/myproject" in script
    assert "claude --resume abc123" in script


def test_open_terminal_and_resume_appends_configured_extra_args():
    captured = {}
    def fake_runner(cmd, check):
        captured["cmd"] = cmd
    config = Config(claude_extra_args="--dangerously-skip-permissions")
    open_terminal_and_resume("abc123", "/Users/x/Code/myproject", UPDATED_AT, config=config, runner=fake_runner,
                             path_exists=lambda p: True)
    script = captured["cmd"][2]
    assert "claude --resume abc123 --dangerously-skip-permissions" in script


def test_applescript_escape_neutralizes_quotes_backslashes_newlines():
    assert _applescript_escape('say "hi"') == 'say \\"hi\\"'
    assert _applescript_escape("a\\b") == "a\\\\b"
    assert _applescript_escape("line1\nline2") == "line1\\nline2"


def test_open_terminal_and_resume_escapes_prompt_newlines_for_applescript():
    # AppleScript string literals cannot contain raw newlines; the injected prompt's blank
    # line (\n\n) would otherwise make `do script "..."` fail to compile. It must be escaped
    # to backslash-n so no raw double-newline survives inside the script.
    captured = {}
    def fake_runner(cmd, check):
        captured["cmd"] = cmd
    open_terminal_and_resume("abc123", "/Users/x/Code/myproject", UPDATED_AT, runner=fake_runner, now=NOW,
                             path_exists=lambda p: True)
    script = captured["cmd"][2]
    assert "\n\n" not in script      # no raw blank line leaked into the AppleScript literal
    assert "\\n\\n" in script        # the prompt's blank line is present, escaped


def test_open_terminal_and_resume_escapes_double_quote_in_cwd():
    # A project path containing a double quote must not break out of the AppleScript
    # `do script "..."` string literal (which would let the remainder run as AppleScript --
    # arbitrary command execution). The quote must be escaped for the AppleScript layer, not
    # just the shell layer (shlex.quote leaves a `"` literal inside its single quotes).
    captured = {}
    def fake_runner(cmd, check):
        captured["cmd"] = cmd
    open_terminal_and_resume("abc123", '/Users/x/Code/proj"evil', UPDATED_AT, runner=fake_runner,
                             path_exists=lambda p: True)
    script = captured["cmd"][2]
    assert 'proj\\"evil' in script    # the path's quote is AppleScript-escaped
    assert 'proj"evil' not in script  # no unescaped quote that could terminate the literal


def test_open_terminal_and_resume_raises_when_directory_missing(tmp_path):
    # If the project directory was deleted/renamed, `cd <dir> && claude` would silently no-op in
    # the terminal while osascript still exits 0. Refuse to launch, so the server surfaces an
    # error instead of falsely reporting the session resumed.
    missing = str(tmp_path / "was-deleted")  # never created; uses the real os.path.isdir default
    def runner_should_not_run(cmd, check):
        raise AssertionError("osascript must not run when the project directory is missing")
    with pytest.raises(FileNotFoundError, match="was-deleted"):
        open_terminal_and_resume("abc123", missing, UPDATED_AT, runner=runner_should_not_run)
