# ABOUTME: pytest fixture providing a temporary ccrider SQLite DB with the schema subset.
# ABOUTME: Helpers add_session and add_message for test data setup.
import sqlite3
import pytest


@pytest.fixture
def ccrider_db(tmp_path):
    db = tmp_path / "sessions.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE sessions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          session_id TEXT, project_path TEXT, cwd TEXT, summary TEXT, llm_summary TEXT,
          created_at DATETIME, updated_at DATETIME, message_count INTEGER,
          git_branch TEXT, provider TEXT
        );
        CREATE TABLE messages (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          session_id INTEGER, uuid TEXT, parent_uuid TEXT, type TEXT, sender TEXT,
          content TEXT, text_content TEXT, timestamp DATETIME,
          is_sidechain INTEGER, sequence INTEGER
        );
        """
    )
    conn.commit()
    conn.close()
    return db


def add_session(db, session_id, project_path, updated_at,
                created_at="2026-01-01 00:00:00", message_count=10,
                llm_summary=None, summary=None):
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO sessions(session_id,project_path,cwd,summary,llm_summary,created_at,updated_at,message_count)"
        " VALUES(?,?,?,?,?,?,?,?)",
        (session_id, project_path, project_path, summary, llm_summary, created_at, updated_at, message_count),
    )
    conn.commit()
    conn.close()


def add_message(db, session_id, role, body, sequence, is_sidechain=0):
    sender = "human" if role == "user" else role
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO messages(session_id,type,sender,content,text_content,is_sidechain,sequence)"
        " VALUES((SELECT id FROM sessions WHERE session_id=?),?,?,?,?,?,?)",
        (session_id, role, sender, body, body, is_sidechain, sequence),
    )
    conn.commit()
    conn.close()
