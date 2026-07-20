# ABOUTME: Tests for claude_runner-backed recap generation and ensure_recaps caching/pooling.
# ABOUTME: Uses injected fake runners so no real `claude` process is ever spawned.
import tempfile

from reconvene.config import Config
from reconvene.db import Session
from reconvene.journal import Project
from reconvene.recap import build_prompt, claude_runner, ensure_recaps, excerpt, generate_recap, RecapCache


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


def test_ensure_recaps_surfaces_llm_failure_and_does_not_cache_the_degraded_result(tmp_path, ccrider_db, capsys):
    # An LLM failure must NOT be silently swallowed, and the degraded first-message fallback must
    # NOT be cached under the valid signature -- otherwise a transient failure (e.g. a bad key)
    # sticks as a stale non-LLM recap even after the cause is fixed.
    p = _project(ccrider_db, "myproject")
    cache = RecapCache(tmp_path / "r.db")
    config = Config()  # claude_cli -> use_llm True
    calls = []
    def flaky(prompt):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("claude failed")
        return "ONELINE: real recap\nDETAIL: real detail"

    r1 = ensure_recaps([p], ccrider_db, cache, config, runner=flaky)
    assert r1["myproject"][0].startswith("do the thing")   # degraded fallback returned this run
    assert "failed" in capsys.readouterr().err             # error surfaced, not swallowed

    r2 = ensure_recaps([p], ccrider_db, cache, config, runner=flaky)
    assert r2["myproject"][0] == "real recap"              # regenerated: the degraded result was not cached
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


def test_excerpt_returns_first_three_sentences():
    detail = "Sentence one. Sentence two. Sentence three. Sentence four. Sentence five."
    assert excerpt(detail) == "Sentence one. Sentence two. Sentence three."


def test_excerpt_returns_whole_text_when_fewer_sentences_than_limit():
    detail = "Only one sentence here."
    assert excerpt(detail) == "Only one sentence here."


def test_excerpt_collapses_newlines_between_sentences():
    detail = "Sentence one.\nSentence two.\n\nSentence three. Sentence four."
    assert excerpt(detail) == "Sentence one. Sentence two. Sentence three."


def test_excerpt_handles_empty_string():
    assert excerpt("") == ""


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


def test_claude_runner_strips_inherited_api_key_in_cli_mode(monkeypatch):
    # Default claude_cli mode must run recaps on the user's Claude subscription. If the user
    # has ANTHROPIC_API_KEY exported in their shell, an inherited key would silently bill their
    # API account per-token instead -- so it must be stripped from the child env.
    captured = {}

    def fake_run(cmd, capture_output, text, env, timeout, cwd):
        captured["env"] = env
        class Result:
            returncode = 0
            stdout = "ONELINE: ok\nDETAIL: ok"
        return Result()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-inherited-from-shell")
    monkeypatch.setattr("reconvene.recap.subprocess.run", fake_run)
    claude_runner("a prompt", Config())  # default recap_auth_mode="claude_cli"
    assert "ANTHROPIC_API_KEY" not in captured["env"]


def _session(sid="s1", path="/Users/x/Code/myproject", updated="2026-07-08 10:00:00", count=12):
    return Session(sid, path, updated, updated, count, None, None)


def test_ensure_session_recap_generates_via_runner_and_caches(tmp_path, ccrider_db):
    from tests.conftest import add_session, add_message
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 10:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "tune the nas raid", sequence=1)
    from reconvene.recap import ensure_session_recap
    calls = []
    def runner(prompt):
        calls.append(prompt)
        return "ONELINE: nas tune-up\nDETAIL: worked on the synology raid"
    cache = RecapCache(str(tmp_path / "r.db"))
    one, full = ensure_session_recap(_session(), str(ccrider_db), cache, Config(), runner=runner)
    assert one == "nas tune-up" and "synology raid" in full
    assert len(calls) == 1
    # second call is a cache hit — runner not invoked again
    ensure_session_recap(_session(), str(ccrider_db), cache, Config(), runner=runner)
    assert len(calls) == 1
    cache.close()


def test_ensure_session_recap_none_auth_derives_without_runner(tmp_path, ccrider_db):
    from tests.conftest import add_session, add_message
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 10:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "tune the nas raid", sequence=1)
    from reconvene.recap import ensure_session_recap
    calls = []
    cache = RecapCache(str(tmp_path / "r.db"))
    one, full = ensure_session_recap(_session(), str(ccrider_db), cache,
                                     Config(recap_auth_mode="none"),
                                     runner=lambda p: calls.append(p) or "")
    assert "tune the nas raid" in full
    assert calls == []  # no claude call in none mode
    cache.close()


def test_ensure_session_recap_key_does_not_collide_with_project(tmp_path, ccrider_db):
    from tests.conftest import add_session, add_message
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 10:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "hi", sequence=1)
    from reconvene.recap import ensure_session_recap, signature
    cache = RecapCache(str(tmp_path / "r.db"))
    # A project recap stored under the bare name must not be returned as a session recap.
    cache.put("s1", signature([_session()]), "proj one", "project recap body")
    _, full = ensure_session_recap(_session(), str(ccrider_db), cache,
                                   Config(recap_auth_mode="none"), runner=lambda p: "")
    assert full != "project recap body"  # session recap is namespaced (session:s1)
    cache.close()


def test_build_session_prompt_includes_transcript(ccrider_db):
    from tests.conftest import add_session, add_message
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 10:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "summarize the raid migration", sequence=1)
    from reconvene.recap import build_session_prompt
    prompt = build_session_prompt(_session(), str(ccrider_db))
    assert "summarize the raid migration" in prompt
    assert "ONELINE:" in prompt and "DETAIL:" in prompt
