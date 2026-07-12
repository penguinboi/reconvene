# ABOUTME: Tests for read-only ccrider DB access.
# ABOUTME: Verifies row loading, schema validation, and read-only connection mode.
import sqlite3

import pytest

from reconvene.db import load_sessions, probe_schema, session_messages
from tests.conftest import add_session, add_message


def test_load_sessions_reads_rows(ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/regrade3", "2026-07-08 10:00:00", message_count=42)
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
    add_session(ccrider_db, "s1", "/Users/x/Code/regrade3", "2026-07-08 10:00:00")
    load_sessions(str(ccrider_db))  # must not raise or lock the file
    # a second independent connection must still be able to write (proves the
    # read-only connection didn't hold a lock)
    conn = sqlite3.connect(ccrider_db)
    conn.execute("UPDATE sessions SET message_count = 99 WHERE session_id = 's1'")
    conn.commit()
    conn.close()


def test_session_messages_orders_and_skips_sidechain(ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/regrade3", "2026-07-08 10:00:00")
    add_message(ccrider_db, "s1", "assistant", "hi", sequence=1)
    add_message(ccrider_db, "s1", "user", "do the sensor task", sequence=2)
    add_message(ccrider_db, "s1", "user", "side note", sequence=3, is_sidechain=1)
    msgs = session_messages(str(ccrider_db), "s1")
    assert msgs == [("assistant", "hi"), ("user", "do the sensor task")]
