# ABOUTME: Tests for building the resume command and the macOS terminal-launch automation.
# ABOUTME: Injects a fake subprocess runner so no real Terminal window is ever opened in tests.
import pytest

from reconvene.resume import open_terminal_and_resume, resume_command


def test_resume_command():
    assert resume_command("abc123") == ["claude", "--resume", "abc123"]


def test_open_terminal_and_resume_runs_osascript():
    captured = {}
    def fake_runner(cmd, check):
        captured["cmd"] = cmd
        captured["check"] = check
    open_terminal_and_resume("abc123", "/Users/x/Code/myproject", runner=fake_runner)
    assert captured["cmd"][0] == "osascript"
    assert captured["cmd"][1] == "-e"
    script = captured["cmd"][2]
    assert "Terminal" in script
    assert "activate" in script  # brings the new window to the foreground, not just spawns it silently
    assert "/Users/x/Code/myproject" in script
    assert "claude --resume abc123" in script
    assert captured["check"] is True


def test_open_terminal_and_resume_raises_on_failure():
    def failing_runner(cmd, check):
        raise RuntimeError("osascript not found")
    with pytest.raises(RuntimeError, match="osascript not found"):
        open_terminal_and_resume("abc123", "/Users/x/Code/myproject", runner=failing_runner)
