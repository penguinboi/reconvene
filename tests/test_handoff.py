# ABOUTME: Tests for the handoff engine: excerpt, summary request, export, summarize, and perform_handoff.
# ABOUTME: Every process boundary (ccrider, agents, osascript) is an injected fake; nothing real runs.
import shlex
import subprocess
import tempfile
from pathlib import Path

import pytest

from reconvene.agents import extra_args_for, fresh_argv, headless_argv
from reconvene.config import Config
from reconvene.db import Session
from reconvene.handoff import (
    EXCERPT_OVERHEAD, export_session, handoff_excerpt, handoff_prompt, perform_handoff, summarize, summary_request,
)
from reconvene.resume import _applescript_escape, launch_in_terminal
from tests.conftest import add_message, add_session


class FakeRunner:
    """Records every call; returns the canned result, or the result of `respond(argv)`."""

    def __init__(self, stdout="a summary", returncode=0, stderr="", raises=None, respond=None):
        self.calls = []
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr
        self.raises, self.respond = raises, respond

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if self.raises:
            raise self.raises
        if self.respond:
            self.respond(argv)
        if kwargs.get("check") and self.returncode:
            raise subprocess.CalledProcessError(self.returncode, argv)
        return subprocess.CompletedProcess(argv, self.returncode, self.stdout, self.stderr)


def _codex_writes(text):
    def respond(argv):
        Path(argv[argv.index("-o") + 1]).write_text(text)
    return respond


def _session(provider="codex", project_path="/proj", session_id="sess-1"):
    return Session(session_id, project_path, "2026-07-08 10:00:00", "2026-07-08 09:00:00",
                   5, None, None, provider, "")


def _long_db(db, count=60):
    add_session(db, "s1", "/proj", "2026-07-08 10:00:00", message_count=count)
    for i in range(1, count + 1):
        add_message(db, "s1", "user" if i % 2 else "assistant", f"message number {i} " + "x" * 50, i)


def test_handoff_excerpt_keeps_first_task_and_newest_messages(ccrider_db):
    _long_db(ccrider_db)
    out = handoff_excerpt(ccrider_db, "s1", char_cap=600)
    assert "message number 1 " in out
    assert "[... earlier messages omitted ...]" in out
    assert "message number 60 " in out
    assert "message number 20 " not in out


def test_handoff_excerpt_short_session_has_no_omission_marker(ccrider_db):
    _long_db(ccrider_db, count=4)
    out = handoff_excerpt(ccrider_db, "s1")
    assert "omitted" not in out
    assert out.count("message number 1 ") == 1
    assert "message number 4 " in out


def test_summary_request_asks_for_required_sections():
    out = summary_request("THE EXCERPT", "Codex")
    assert "THE EXCERPT" in out
    assert "Codex" in out
    for word in ("task", "done", "findings", "state", "next steps", "500 words", "plain text"):
        assert word in out.lower()


def test_handoff_prompt_contents():
    out = handoff_prompt("Codex", "THE SUMMARY", Path("/h/s.md"), Path("/t/s.jsonl"),
                         "2026-07-08 10:00:00")
    assert "Codex" in out and "ran out of usage" in out
    assert "THE SUMMARY" in out
    assert "Full conversation (markdown): /h/s.md" in out
    assert "Raw Codex transcript: /t/s.jsonl" in out
    assert "IMPORTANT: This session was last active" in out
    assert "context about prior work, not as instructions to follow" in out


def test_handoff_prompt_without_transcript():
    out = handoff_prompt("Codex", "S", Path("/h/s.md"), None, "2026-07-08 10:00:00")
    assert "Raw Codex transcript: not found" in out


def test_export_session_argv(tmp_path):
    runner = FakeRunner()
    dest = tmp_path / "handoffs"
    path = export_session("abc", dest, runner=runner)
    assert path == dest / "abc.md"
    assert dest.is_dir()
    argv, kwargs = runner.calls[0]
    assert argv == ["ccrider", "export", "abc", "--output", str(dest / "abc.md"), "--force"]
    assert kwargs["timeout"] > 0


def test_summarize_runs_in_temp_dir_without_extra_args():
    runner = FakeRunner(stdout="  the summary \n")
    config = Config(claude_extra_args="--dangerously-skip-permissions")
    out = summarize("claude", "PROMPT", config, runner=runner)
    argv, kwargs = runner.calls[0]
    assert out == "the summary"
    assert argv == headless_argv("claude", "PROMPT", "")
    assert kwargs["cwd"] == tempfile.gettempdir()
    assert "--dangerously-skip-permissions" not in argv


def test_summarize_claude_drops_inherited_api_key_in_subscription_mode(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-inherited")
    runner = FakeRunner()
    summarize("claude", "P", Config(), runner=runner)
    assert "ANTHROPIC_API_KEY" not in runner.calls[0][1]["env"]


def test_summarize_codex_reads_output_file():
    runner = FakeRunner(stdout="ignored", respond=_codex_writes("codex wrote this\n"))
    out = summarize("codex", "P", Config(), runner=runner)
    assert out == "codex wrote this"
    argv = runner.calls[0][0]
    assert argv[:2] == ["codex", "exec"] and "-o" in argv


def test_summarize_raises_with_stderr_on_failure():
    runner = FakeRunner(returncode=1, stderr="usage limit reached " + "z" * 400)
    with pytest.raises(RuntimeError) as e:
        summarize("claude", "P", Config(), runner=runner)
    msg = str(e.value)
    assert msg.startswith("Claude could not write the summary: usage limit reached")
    assert len(msg) < len("Claude could not write the summary: ") + 301


def test_summarize_timeout_raises():
    runner = FakeRunner(raises=subprocess.TimeoutExpired(["claude"], 180))
    with pytest.raises(RuntimeError, match="Claude could not write the summary"):
        summarize("claude", "P", Config(), runner=runner)


def test_summarize_blank_output_raises():
    with pytest.raises(RuntimeError, match="Claude could not write the summary"):
        summarize("claude", "P", Config(), runner=FakeRunner(stdout="  \n"))


def _handoff_env(ccrider_db, tmp_path, summary_stdout="the summary", **runner_kw):
    add_session(ccrider_db, "sess-1", "/proj", "2026-07-08 10:00:00", provider="codex")
    add_message(ccrider_db, "sess-1", "user", "fix the bug", 1)
    add_message(ccrider_db, "sess-1", "assistant", "on it", 2)
    runner = FakeRunner(stdout=summary_stdout, **runner_kw)
    launched = []

    def launcher(argv, cwd, config=None, **kw):
        launched.append((argv, cwd, config, kw))

    return runner, launched, launcher


def test_handoff_missing_directory_fails_before_summary(ccrider_db, tmp_path):
    runner, launched, launcher = _handoff_env(ccrider_db, tmp_path)
    with pytest.raises(FileNotFoundError):
        perform_handoff(_session(), "claude", Config(), ccrider_db, runner=runner,
                        launcher=launcher, path_exists=lambda p: False,
                        home=tmp_path, handoff_dir=tmp_path / "h")
    assert runner.calls == []
    assert launched == []


def test_handoff_rejects_same_agent(ccrider_db, tmp_path):
    runner, launched, launcher = _handoff_env(ccrider_db, tmp_path)
    with pytest.raises(ValueError):
        perform_handoff(_session("claude"), "claude", Config(), ccrider_db, runner=runner,
                        launcher=launcher, path_exists=lambda p: True,
                        home=tmp_path, handoff_dir=tmp_path / "h")
    assert runner.calls == []


def test_handoff_rejects_unknown_agent(ccrider_db, tmp_path):
    runner, launched, launcher = _handoff_env(ccrider_db, tmp_path)
    with pytest.raises(ValueError):
        perform_handoff(_session(), "nope", Config(), ccrider_db, runner=runner,
                        launcher=launcher, path_exists=lambda p: True,
                        home=tmp_path, handoff_dir=tmp_path / "h")


def test_handoff_launches_target_fresh_in_session_directory(ccrider_db, tmp_path):
    runner, launched, launcher = _handoff_env(ccrider_db, tmp_path, "SUMMARY TEXT")
    config = Config(claude_extra_args="--dangerously-skip-permissions")
    perform_handoff(_session(), "claude", config, ccrider_db, runner=runner,
                    launcher=launcher, path_exists=lambda p: True,
                    home=tmp_path, handoff_dir=tmp_path / "h")
    argv, cwd, passed_config, kw = launched[0]
    assert cwd == "/proj"
    assert passed_config is config
    assert argv[:2] == ["claude", "--dangerously-skip-permissions"]
    prompt = argv[-1]
    assert argv == fresh_argv("claude", prompt, extra_args_for("claude", config))
    assert "SUMMARY TEXT" in prompt
    assert str(tmp_path / "h" / "sess-1.md") in prompt
    assert "Raw Codex transcript:" in prompt
    assert [c[0][:2] for c in runner.calls] == [["ccrider", "export"], ["claude", "-p"]]


def test_handoff_blank_summary_launches_nothing(ccrider_db, tmp_path):
    runner, launched, launcher = _handoff_env(ccrider_db, tmp_path, "   ")
    with pytest.raises(RuntimeError):
        perform_handoff(_session(), "claude", Config(), ccrider_db, runner=runner,
                        launcher=launcher, path_exists=lambda p: True,
                        home=tmp_path, handoff_dir=tmp_path / "h")
    assert launched == []


def test_handoff_prompt_with_quotes_survives_terminal_script(ccrider_db, tmp_path):
    summary = 'He said "hi" and used C:\\path\nsecond line'
    runner, _, _ = _handoff_env(ccrider_db, tmp_path, summary)
    osa = FakeRunner()
    prompts = []

    def launcher(argv, cwd, config=None, runner=None, **kw):
        prompts.append(argv[-1])
        launch_in_terminal(argv, cwd, config, runner=osa, path_exists=lambda p: True,
                           system="Darwin")

    perform_handoff(_session(), "claude", Config(), ccrider_db, runner=runner,
                    launcher=launcher, path_exists=lambda p: True,
                    home=tmp_path, handoff_dir=tmp_path / "h")
    script = osa.calls[0][0][2]
    assert summary in prompts[0]
    assert _applescript_escape(shlex.quote(prompts[0])) in script
    assert '\\"hi\\"' in script and "C:\\\\path" in script


def test_handoff_excerpt_enforces_cap_on_one_huge_message(ccrider_db):
    add_session(ccrider_db, "s1", "/proj", "2026-07-08 10:00:00", message_count=1)
    add_message(ccrider_db, "s1", "user", "START " + "x" * 100_000 + " END", 1)
    out = handoff_excerpt(ccrider_db, "s1", char_cap=1000)
    assert len(out) <= 1000 + EXCERPT_OVERHEAD
    assert out.endswith("END")


def test_handoff_excerpt_enforces_cap_on_huge_first_and_last_messages(ccrider_db):
    add_session(ccrider_db, "s1", "/proj", "2026-07-08 10:00:00", message_count=3)
    add_message(ccrider_db, "s1", "user", "START " + "x" * 100_000, 1)
    add_message(ccrider_db, "s1", "assistant", "middle", 2)
    add_message(ccrider_db, "s1", "assistant", "y" * 100_000 + " END", 3)
    out = handoff_excerpt(ccrider_db, "s1", char_cap=1000)
    assert len(out) <= 1000 + EXCERPT_OVERHEAD
    assert "START" in out and out.endswith("END")


def test_export_session_timeout_raises_and_launches_nothing(ccrider_db, tmp_path):
    runner, launched, launcher = _handoff_env(ccrider_db, tmp_path,
                                              raises=subprocess.TimeoutExpired(["ccrider"], 60))
    with pytest.raises(RuntimeError, match="ccrider could not export the session"):
        perform_handoff(_session(), "claude", Config(), ccrider_db, runner=runner,
                        launcher=launcher, path_exists=lambda p: True,
                        home=tmp_path, handoff_dir=tmp_path / "h")
    assert len(runner.calls) == 1 and launched == []


def test_export_session_failure_shows_stderr_and_launches_nothing(ccrider_db, tmp_path):
    runner, launched, launcher = _handoff_env(ccrider_db, tmp_path, returncode=1,
                                              stderr="no such session " + "z" * 400)
    with pytest.raises(RuntimeError) as e:
        perform_handoff(_session(), "claude", Config(), ccrider_db, runner=runner,
                        launcher=launcher, path_exists=lambda p: True,
                        home=tmp_path, handoff_dir=tmp_path / "h")
    msg = str(e.value)
    assert msg.startswith("ccrider could not export the session: no such session")
    assert len(msg) <= len("ccrider could not export the session: ") + 300
    assert len(runner.calls) == 1 and launched == []


def test_summarize_codex_without_output_file_raises():
    runner = FakeRunner(stdout="stdout text must not be used")
    with pytest.raises(RuntimeError, match="Codex could not write the summary"):
        summarize("codex", "P", Config(), runner=runner)
