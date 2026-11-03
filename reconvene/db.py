# ABOUTME: Read-only access to ccrider's SQLite session DB (sessions + messages tables).
# ABOUTME: Fails loudly if ccrider's schema drifts; never writes to the DB.
import sqlite3
from dataclasses import dataclass

REQUIRED_SESSION_COLS = {
    "session_id", "project_path", "summary", "llm_summary",
    "created_at", "updated_at", "message_count", "provider", "resume_via",
}


@dataclass(frozen=True)
class Session:
    session_id: str
    project_path: str
    updated_at: str
    created_at: str
    message_count: int
    llm_summary: str | None
    summary: str | None
    provider: str
    resume_via: str


def _connect(db_path):
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def probe_schema(conn):
    conn.row_factory = sqlite3.Row
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(sessions)")}
    missing = REQUIRED_SESSION_COLS - cols
    if missing:
        raise RuntimeError(
            f"ccrider sessions table missing columns: {sorted(missing)} — ccrider schema changed?"
        )


_SESSION_SELECT = (
    "SELECT session_id, project_path, summary, llm_summary, created_at, updated_at, "
    "message_count, provider, resume_via FROM sessions"
)


def _session_from_row(r) -> Session:
    return Session(
        r["session_id"], r["project_path"], r["updated_at"], r["created_at"],
        r["message_count"] or 0, r["llm_summary"], r["summary"],
        r["provider"] or "claude", r["resume_via"] or "",
    )


def load_sessions(db_path) -> list[Session]:
    conn = _connect(db_path)
    try:
        probe_schema(conn)
        rows = conn.execute(_SESSION_SELECT + " WHERE COALESCE(resume_via, '') = ''").fetchall()
    finally:
        conn.close()
    return [_session_from_row(r) for r in rows]


def find_session(db_path, session_id) -> Session | None:
    conn = _connect(db_path)
    try:
        probe_schema(conn)
        row = conn.execute(_SESSION_SELECT + " WHERE session_id = ?", (session_id,)).fetchone()
    finally:
        conn.close()
    return _session_from_row(row) if row else None


def session_messages(db_path, session_id, limit=40, newest=False) -> list[tuple[str, str]]:
    order = "DESC" if newest else "ASC"
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT type, COALESCE(NULLIF(text_content,''), content) AS body "
            "FROM messages WHERE session_id = (SELECT id FROM sessions WHERE session_id=?) "
            "AND (is_sidechain IS NULL OR is_sidechain=0) "
            f"ORDER BY sequence {order} LIMIT ?",
            (session_id, limit),
        ).fetchall()
    finally:
        conn.close()
    if newest:
        rows.reverse()
    out = []
    for r in rows:
        body = (r["body"] or "").strip()
        if body:
            out.append(((r["type"] or ""), body))
    return out
