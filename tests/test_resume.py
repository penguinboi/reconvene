# ABOUTME: Tests for building the resume command and the macOS terminal-launch automation.
# ABOUTME: Injects a fake subprocess runner so no real Terminal window is ever opened in tests.
import shlex
from datetime import datetime

import pytest

from reconvene.config import Config
from reconvene.resume import open_terminal_and_resume, resume_command, resume_prompt

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
    open_terminal_and_resume("abc123", "/Users/x/Code/myproject", UPDATED_AT, runner=fake_runner)
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
        open_terminal_and_resume("abc123", "/Users/x/Code/myproject", UPDATED_AT, runner=failing_runner)


def test_open_terminal_and_resume_uses_iterm2_when_configured():
    captured = {}
    def fake_runner(cmd, check):
        captured["cmd"] = cmd
    config = Config(terminal_app="iTerm2")
    open_terminal_and_resume("abc123", "/Users/x/Code/myproject", UPDATED_AT, config=config, runner=fake_runner)
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
    open_terminal_and_resume("abc123", "/Users/x/Code/myproject", UPDATED_AT, config=config, runner=fake_runner)
    script = captured["cmd"][2]
    assert "claude --resume abc123 --dangerously-skip-permissions" in script


def test_open_terminal_and_resume_shell_quotes_the_multiline_prompt():
    # The injected prompt contains spaces and an embedded blank line -- naively joining argv
    # elements with a bare space (as this used to do) would produce invalid/broken shell text
    # once "typed" into a real Terminal/iTerm2 session. Each argv element must be shell-quoted.
    captured = {}
    def fake_runner(cmd, check):
        captured["cmd"] = cmd
    open_terminal_and_resume("abc123", "/Users/x/Code/myproject", UPDATED_AT, runner=fake_runner, now=NOW)
    script = captured["cmd"][2]
    assert shlex.quote(resume_prompt(UPDATED_AT, NOW)) in script
