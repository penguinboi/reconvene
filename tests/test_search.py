# ABOUTME: Tests for FTS5-backed session search — sanitization, ranking, snippets, errors.
# ABOUTME: Runs against the fixture's real FTS5 external-content table (porter stemming included).
import io
import sqlite3
from contextlib import redirect_stdout

import pytest

from reconvene import _search
from reconvene.search import SNIPPET_CLOSE, SNIPPET_OPEN, sanitize_query, search_sessions
from tests.conftest import add_session, add_message


def test_sanitize_quotes_each_token():
    assert sanitize_query("pi-hole nas") == '"pi-hole" "nas"'


def test_sanitize_strips_embedded_quotes():
    assert sanitize_query('drop "tables" now') == '"drop" "tables" "now"'


def test_sanitize_empty_and_whitespace():
    assert sanitize_query("") == ""
    assert sanitize_query("   ") == ""


def test_search_empty_query_returns_no_hits(ccrider_db):
    assert search_sessions(str(ccrider_db), "   ") == []


def test_search_ranks_by_hit_count(ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/alpha", "2026-07-08 00:00:00", message_count=5)
    add_message(ccrider_db, "s1", "user", "pihole once", sequence=1)
    add_session(ccrider_db, "s2", "/Users/x/Code/beta", "2026-07-01 00:00:00", message_count=5)
    add_message(ccrider_db, "s2", "user", "pihole here", sequence=1)
    add_message(ccrider_db, "s2", "assistant", "pihole again", sequence=2)
    hits = search_sessions(str(ccrider_db), "pihole")
    assert [h.session_id for h in hits] == ["s2", "s1"]
    assert hits[0].hits == 2 and hits[1].hits == 1


def test_search_snippet_wraps_matches_in_markers(ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/alpha", "2026-07-08 00:00:00", message_count=5)
    add_message(ccrider_db, "s1", "user", "tuning the synology nas today", sequence=1)
    (hit,) = search_sessions(str(ccrider_db), "synology")
    assert f"{SNIPPET_OPEN}synology{SNIPPET_CLOSE}" in hit.snippet


def test_search_uses_porter_stemming(ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/alpha", "2026-07-08 00:00:00", message_count=5)
    add_message(ccrider_db, "s1", "user", "cleaning the desktop", sequence=1)
    assert len(search_sessions(str(ccrider_db), "cleaned")) == 1


def test_search_missing_fts_table_raises_clear_error(tmp_path):
    raw = tmp_path / "nofts.db"
    conn = sqlite3.connect(raw)
    conn.executescript(
        "CREATE TABLE sessions (id INTEGER PRIMARY KEY, session_id TEXT, project_path TEXT,"
        " summary TEXT, llm_summary TEXT, created_at TEXT, updated_at TEXT, message_count INT);"
        "CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id INT, text_content TEXT);"
    )
    conn.close()
    with pytest.raises(RuntimeError, match="messages_fts"):
        search_sessions(str(raw), "anything")


def test_search_module_prints_tab_delimited_lines(ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/homelab", "2026-07-08 00:00:00", message_count=9)
    add_message(ccrider_db, "s1", "user", "pihole dns setup", sequence=1)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = _search.main(["pihole", str(ccrider_db)])
    assert rc == 0
    line = buf.getvalue().strip()
    sid, display = line.split("\t", 1)
    assert sid == "s1"
    assert "homelab" in display and "1✓" in display
    assert "«" not in display and "»" not in display  # markers stripped for terminal


def test_search_module_empty_query_prints_nothing(ccrider_db):
    buf = io.StringIO()
    with redirect_stdout(buf):
        _search.main(["", str(ccrider_db)])
    assert buf.getvalue() == ""
