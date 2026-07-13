# ABOUTME: Tests for claude_runner-backed recap generation and ensure_recaps caching/pooling.
# ABOUTME: Uses injected fake runners so no real `claude` process is ever spawned.
import tempfile

from reconvene.config import Config
from reconvene.db import Session
from reconvene.journal import Project
from reconvene.recap import build_prompt, claude_runner, ensure_recaps, generate_recap, RecapCache


def _project(db, name):
    from tests.conftest import add_session, add_message
    add_session(db, "s1", f"/Users/x/Code/{name}", "2026-07-08 10:00:00", message_count=5)
    add_message(db, "s1", "user", "do the thing", sequence=1)
    return Project(name, "real", [Session("s1", f"/Users/x/Code/{name}", "2026-07-08 10:00:00", "x", 5, None, None)])


def test_build_prompt_asks_for_multi_paragraph_detail(ccrider_db):
    p = _project(ccrider_db, "myproject")
    prompt = build_prompt(p, ccrider_db)
    assert "multi-paragraph" in prompt
    assert "600 words" in prompt


def test_build_prompt_default_char_budget_covers_a_long_session(ccrider_db):
    from tests.conftest import add_session, add_message
    add_session(ccrider_db, "s2", "/Users/x/Code/myproject", "2026-07-09 10:00:00", message_count=1)
    long_body = "x" * 5000  # longer than the old 2000-char-per-session budget
    add_message(ccrider_db, "s2", "user", long_body, sequence=1)
    p = Project("myproject", "real", [
        Session("s2", "/Users/x/Code/myproject", "2026-07-09 10:00:00", "x", 1, None, None),
    ])
    prompt = build_prompt(p, ccrider_db)
    assert long_body in prompt


def test_generate_recap_uses_injected_runner(ccrider_db):
    p = _project(ccrider_db, "myproject")
    fake = lambda prompt: "ONELINE: did the thing\nDETAIL: all good"
    one, full = generate_recap(p, ccrider_db, runner=fake)
    assert one == "did the thing"


def test_ensure_recaps_caches_and_reuses(tmp_path, ccrider_db):
    p = _project(ccrider_db, "myproject")
    cache = RecapCache(tmp_path / "r.db")
    config = Config()
    calls = []
    def runner(prompt):
        calls.append(1)
        return "ONELINE: cached me\nDETAIL: x"
    r1 = ensure_recaps([p], ccrider_db, cache, config, runner=runner)
    r2 = ensure_recaps([p], ccrider_db, cache, config, runner=runner)  # signature unchanged -> cache hit
    assert r1["myproject"][0] == "cached me"
    assert r2["myproject"][0] == "cached me"
    assert len(calls) == 1
    cache.close()


def test_ensure_recaps_skips_llm_when_auth_mode_none(tmp_path, ccrider_db):
    p = _project(ccrider_db, "myproject")
    cache = RecapCache(tmp_path / "r.db")
    config = Config(recap_auth_mode="none")
    calls = []
    def runner(prompt):
        calls.append(1)
        return "ONELINE: should not be called\nDETAIL: x"
    r = ensure_recaps([p], ccrider_db, cache, config, runner=runner)
    assert calls == []  # runner never invoked
    assert r["myproject"][0].startswith("do the thing")  # derived fallback
    cache.close()


def test_ensure_recaps_falls_back_on_runner_error(tmp_path, ccrider_db):
    p = _project(ccrider_db, "myproject")
    cache = RecapCache(tmp_path / "r.db")
    config = Config()
    def boom(prompt):
        raise RuntimeError("claude failed")
    r = ensure_recaps([p], ccrider_db, cache, config, runner=boom)
    assert r["myproject"][0].startswith("do the thing")
    cache.close()


def test_claude_runner_runs_in_neutral_cwd(monkeypatch):
    captured = {}

    def fake_run(cmd, capture_output, text, env, timeout, cwd):
        captured["cwd"] = cwd
        captured["env"] = env
        class Result:
            returncode = 0
            stdout = "ONELINE: ok\nDETAIL: ok"
        return Result()

    monkeypatch.setattr("reconvene.recap.subprocess.run", fake_run)
    claude_runner("a prompt", Config())
    assert captured["cwd"] == tempfile.gettempdir()


def test_claude_runner_sets_api_key_when_configured(monkeypatch):
    captured = {}

    def fake_run(cmd, capture_output, text, env, timeout, cwd):
        captured["env"] = env
        class Result:
            returncode = 0
            stdout = "ONELINE: ok\nDETAIL: ok"
        return Result()

    monkeypatch.setattr("reconvene.recap.subprocess.run", fake_run)
    claude_runner("a prompt", Config(recap_auth_mode="api_key", api_key="sk-test"))
    assert captured["env"]["ANTHROPIC_API_KEY"] == "sk-test"
