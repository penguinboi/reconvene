# ABOUTME: Tests for the agent registry: argv shapes, native session ids, transcript lookup.
# ABOUTME: Pure functions only; no agent binary is ever run.
import pytest

from reconvene.agents import (
    AGENTS,
    extra_args_for,
    fresh_argv,
    get_agent,
    headless_argv,
    installed_agents,
    native_session_id,
    resume_argv,
    transcript_path,
)
from reconvene.config import Config
from reconvene.constants import MODEL
from reconvene.db import Session

CODEX_ID = "01a19a64-6dff-7983-9653-7af460dbd4e9"
CODEX_ROLLOUT = f"rollout-2026-11-01T19-54-00-{CODEX_ID}"


def make_session(session_id="abc", provider="claude", resume_via=""):
    return Session(session_id, "/p", "2026-11-01", "2026-11-01", 3, None, None, provider, resume_via)


def test_agents_registry_order_and_facts():
    assert list(AGENTS) == ["claude", "codex", "antigravity"]
    assert [(a.label, a.binary) for a in AGENTS.values()] == [
        ("Claude", "claude"),
        ("Codex", "codex"),
        ("Antigravity", "agy"),
    ]


def test_get_agent_rejects_unknown():
    with pytest.raises(ValueError, match="unknown agent 'nope'"):
        get_agent("nope")


def test_resume_argv_claude():
    s = make_session("abc", "claude")
    assert resume_argv(s, "hi", ["--x"]) == ["claude", "--resume", "abc", "--x", "hi"]


def test_resume_argv_codex():
    s = make_session(CODEX_ROLLOUT, "codex")
    assert resume_argv(s, "hi", ["--x"]) == ["codex", "resume", "--x", CODEX_ID, "hi"]


def test_resume_argv_antigravity_has_no_prompt():
    s = make_session("conv1", "antigravity")
    assert resume_argv(s, "hi", ["--x"]) == ["agy", "--conversation", "conv1", "--x"]


def test_fresh_argv_each_agent():
    assert fresh_argv("claude", "hi", ["--x"]) == ["claude", "--x", "hi"]
    assert fresh_argv("codex", "hi", ["--x"]) == ["codex", "--x", "hi"]
    assert fresh_argv("antigravity", "hi", ["--x"]) == ["agy", "--x", "-i", "hi"]


def test_headless_argv_each_agent():
    assert headless_argv("claude", "hi", "/o") == [
        "claude", "-p", "--model", MODEL, "--no-session-persistence", "hi",
    ]
    assert headless_argv("codex", "hi", "/o") == [
        "codex", "exec", "--ephemeral", "--skip-git-repo-check", "-s", "read-only", "-o", "/o", "hi",
    ]
    assert headless_argv("antigravity", "hi", "/o") == ["agy", "-p", "hi"]


def test_codex_resume_uses_trailing_uuid():
    assert native_session_id(make_session(CODEX_ROLLOUT, "codex")) == CODEX_ID


def test_codex_resume_prefers_resume_via():
    s = make_session(CODEX_ROLLOUT, "codex", resume_via="parent-uuid")
    assert native_session_id(s) == "parent-uuid"


def test_native_session_id_plain_for_other_agents():
    assert native_session_id(make_session("abc", "claude")) == "abc"


def test_extra_args_for_splits_config_field():
    config = Config(claude_extra_args="--a 'b c'", codex_extra_args="--d", antigravity_extra_args="")
    assert extra_args_for("claude", config) == ["--a", "b c"]
    assert extra_args_for("codex", config) == ["--d"]
    assert extra_args_for("antigravity", config) == []


def test_extra_args_for_none_config_is_empty():
    assert extra_args_for("claude", None) == []


def test_transcript_path_finds_each_agent(tmp_path):
    claude = tmp_path / ".claude/projects/proj/abc.jsonl"
    codex = tmp_path / f".codex/sessions/2026/11/01/{CODEX_ROLLOUT}.jsonl"
    agy = tmp_path / ".gemini/antigravity-cli/conversations/conv1.db"
    for p in (claude, codex, agy):
        p.parent.mkdir(parents=True)
        p.write_text("")
    assert transcript_path(make_session("abc", "claude"), tmp_path) == claude
    assert transcript_path(make_session(CODEX_ROLLOUT, "codex"), tmp_path) == codex
    assert transcript_path(make_session("conv1", "antigravity"), tmp_path) == agy


def test_transcript_path_missing_returns_none(tmp_path):
    assert transcript_path(make_session("abc", "claude"), tmp_path) is None


def test_installed_agents_uses_which():
    found = {"claude": "/bin/claude", "agy": "/bin/agy"}
    assert installed_agents(which=found.get) == {
        "claude": True,
        "codex": False,
        "antigravity": True,
    }
