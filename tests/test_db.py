# ABOUTME: Tests for read-only ccrider DB access.
# ABOUTME: Verifies row loading, schema validation, and read-only connection mode.
import sqlite3

import pytest

from reconvene.db import find_session, load_sessions, probe_schema, session_messages
from tests.conftest import add_session, add_message


def test_load_sessions_reads_rows(ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 10:00:00", message_count=42)
    sessions = load_sessions(str(ccrider_db))
    assert len(sessions) == 1
    assert sessions[0].session_id == "s1"
    assert sessions[0].message_count == 42


def test_probe_schema_raises_on_missing_column(tmp_path):
    db = tmp_path / "broken.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE sessions (id INTEGER PRIMARY KEY)")
    conn.commit()
    with pytest.raises(RuntimeError, match="missing columns"):
        probe_schema(conn)
    conn.close()


def test_connection_is_read_only(ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 10:00:00")
    load_sessions(str(ccrider_db))  # must not raise or lock the file
    # a second independent connection must still be able to write (proves the
    # read-only connection didn't hold a lock)
    conn = sqlite3.connect(ccrider_db)
    conn.execute("UPDATE sessions SET message_count = 99 WHERE session_id = 's1'")
    conn.commit()
    conn.close()


def test_session_messages_orders_and_skips_sidechain(ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 10:00:00")
    add_message(ccrider_db, "s1", "assistant", "hi", sequence=1)
    add_message(ccrider_db, "s1", "user", "do the sensor task", sequence=2)
    add_message(ccrider_db, "s1", "user", "side note", sequence=3, is_sidechain=1)
    msgs = session_messages(str(ccrider_db), "s1")
    assert msgs == [("assistant", "hi"), ("user", "do the sensor task")]


def test_load_sessions_reports_provider(ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/p", "2026-07-08 10:00:00", provider="codex")
    add_session(ccrider_db, "s2", "/Users/x/Code/p", "2026-07-08 10:00:00", provider=None, resume_via=None)
    by_id = {s.session_id: s for s in load_sessions(str(ccrider_db))}
    assert by_id["s1"].provider == "codex"
    assert by_id["s2"].provider == "claude"
    assert by_id["s2"].resume_via == ""


def test_load_sessions_hides_subagent_rows(ccrider_db):
    parent = "01a0f33f-f98b-7121-81e4-10e170c054b4"
    add_session(ccrider_db, "sub1", "/Users/x/Code/p", "2026-07-08 10:00:00",
                provider="codex", resume_via=parent)
    assert load_sessions(str(ccrider_db)) == []
    found = find_session(str(ccrider_db), "sub1")
    assert found is not None
    assert found.resume_via == parent


def test_find_session_returns_none_when_absent(ccrider_db):
    assert find_session(str(ccrider_db), "nope") is None


def test_probe_schema_requires_provider_and_resume_via(tmp_path):
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE sessions (id INTEGER PRIMARY KEY, session_id TEXT, project_path TEXT, summary TEXT, "
        "llm_summary TEXT, created_at TEXT, updated_at TEXT, message_count INTEGER)"
    )
    conn.commit()
    with pytest.raises(RuntimeError, match="provider.*resume_via"):
        probe_schema(conn)
    conn.close()


def test_session_messages_newest_returns_tail_in_order(ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/p", "2026-07-08 10:00:00")
    for n in range(1, 6):
        add_message(ccrider_db, "s1", "user", f"m{n}", sequence=n)
    msgs = session_messages(str(ccrider_db), "s1", limit=2, newest=True)
    assert msgs == [("user", "m4"), ("user", "m5")]
