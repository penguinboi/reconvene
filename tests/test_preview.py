# ABOUTME: Tests for the fzf preview target — cache-first recap rendering, graceful errors.
# ABOUTME: Uses a temp 'none'-mode config so ensure_recaps derives from the first message, no claude.
import io
from contextlib import redirect_stdout

from reconvene.config import Config, save_config
from reconvene.constants import RECENT_SESSIONS_FOR_RECAP
from reconvene.db import load_sessions
from reconvene.journal import build_journal
from reconvene.recap import RecapCache, signature
from reconvene import _preview
from tests.conftest import add_session, add_message


def _none_config(tmp_path):
    p = tmp_path / "config.json"
    save_config(Config(recap_auth_mode="none"), p)
    return str(p)


def _cli_config(tmp_path):
    # Default claude_cli auth — used to exercise the "generating" wait note (a real claude call is
    # avoided by injecting session_recaps_fn).
    p = tmp_path / "cli-config.json"
    save_config(Config(), p)
    return str(p)


def test_preview_unknown_session_prints_not_found(tmp_path, ccrider_db):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = _preview.main(["no-such-sid", str(ccrider_db), str(tmp_path / "r.db"), _none_config(tmp_path)])
    assert rc == 0
    assert "(project not found)" in buf.getvalue()


def test_preview_cache_hit_prints_cached_recap_without_generating(tmp_path, ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "hi", sequence=1)
    config = Config(recap_auth_mode="none")
    project = build_journal(load_sessions(str(ccrider_db)), config)[0][0]
    sig = signature(project.sessions[:RECENT_SESSIONS_FOR_RECAP])
    cache = RecapCache(str(tmp_path / "r.db"))
    cache.put(project.name, sig, "one", "the cached full recap")
    cache.close()

    called = []
    buf = io.StringIO()
    with redirect_stdout(buf):
        _preview.main(["s1", str(ccrider_db), str(tmp_path / "r.db"), _none_config(tmp_path)],
                      recaps_fn=lambda *a: called.append(1) or {})
    out = buf.getvalue()
    assert "the cached full recap" in out
    assert "⏳" not in out    # no loading marker on a hit
    assert called == []       # generation never invoked on a hit


def test_preview_cache_miss_generates_and_prints_recap(tmp_path, ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "wire up the thresholds", sequence=1)
    buf = io.StringIO()
    with redirect_stdout(buf):
        _preview.main(["s1", str(ccrider_db), str(tmp_path / "r.db"), _none_config(tmp_path)])  # real ensure_recaps, none -> derive
    out = buf.getvalue()
    assert "myproject" in out                # header
    assert "wire up the thresholds" in out   # derived recap = first user message
    # No streamed placeholder or terminal escapes: fzf's preview pane can't clear them, so we never
    # print a spinner that would linger above the recap.
    assert "⏳" not in out
    assert "\033[" not in out


def test_preview_generation_failure_is_graceful(tmp_path, ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "hi", sequence=1)
    def boom(*a):
        raise RuntimeError("claude exploded")
    buf = io.StringIO()
    with redirect_stdout(buf):
        _preview.main(["s1", str(ccrider_db), str(tmp_path / "r.db"), _none_config(tmp_path)], recaps_fn=boom)
    out = buf.getvalue()
    assert "⚠ recap unavailable" in out
    assert "claude exploded" in out
    assert "Traceback" not in out


def test_preview_session_mode_uncached_shows_header_note_and_recap(tmp_path, ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "tune the nas raid", sequence=1)
    # claude_cli auth + empty cache = a real generation wait, so the header warns; inject the recap
    # fn so no claude actually runs.
    def fake_session_recap(session, db_path, cache, config):
        assert session.session_id == "s1"
        return ("one liner", "the full generated session recap")
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = _preview.main(["s1", str(ccrider_db), str(tmp_path / "r.db"),
                            _cli_config(tmp_path), "--session"],
                           session_recaps_fn=fake_session_recap)
    out = buf.getvalue()
    assert rc == 0
    assert "myproject" in out                          # header: canonical project name
    assert "12 messages" in out                        # header: message count
    assert "building summary" in out                   # the first-open wait note
    assert "the full generated session recap" in out   # the recap body, not the raw first message


def test_preview_session_mode_cached_shows_no_wait_note(tmp_path, ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "tune the nas raid", sequence=1)
    # Pre-populate the session recap so this is a cache hit — no wait, so no note.
    from reconvene.recap import SESSION_CACHE_PREFIX
    (session,) = load_sessions(str(ccrider_db))
    cache = RecapCache(str(tmp_path / "r.db"))
    cache.put(SESSION_CACHE_PREFIX + "s1", signature([session]), "one", "cached session recap body")
    cache.close()
    buf = io.StringIO()
    with redirect_stdout(buf):
        _preview.main(["s1", str(ccrider_db), str(tmp_path / "r.db"), _cli_config(tmp_path), "--session"])
    out = buf.getvalue()
    assert "cached session recap body" in out
    assert "building summary" not in out               # cache hit → no wait note


def test_preview_session_mode_none_auth_derives_without_note(tmp_path, ccrider_db):
    # recap_auth_mode="none" derives instantly (no claude), so there is no wait and no note.
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "tune the nas raid", sequence=1)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = _preview.main(["s1", str(ccrider_db), str(tmp_path / "r.db"),
                            _none_config(tmp_path), "--session"])
    out = buf.getvalue()
    assert rc == 0
    assert "tune the nas raid" in out
    assert "building summary" not in out


def test_preview_session_mode_recap_failure_is_graceful(tmp_path, ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "hi", sequence=1)
    def boom(*a):
        raise RuntimeError("claude exploded")
    buf = io.StringIO()
    with redirect_stdout(buf):
        _preview.main(["s1", str(ccrider_db), str(tmp_path / "r.db"),
                       _none_config(tmp_path), "--session"], session_recaps_fn=boom)
    out = buf.getvalue()
    assert "⚠ recap unavailable" in out
    assert "claude exploded" in out
    assert "Traceback" not in out


def test_preview_session_mode_unknown_sid(tmp_path, ccrider_db):
    buf = io.StringIO()
    with redirect_stdout(buf):
        _preview.main(["nope", str(ccrider_db), str(tmp_path / "r.db"),
                       _none_config(tmp_path), "--session"])
    assert "(session not found)" in buf.getvalue()
