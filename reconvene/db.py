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


_SQLITE_VARIABLE_CHUNK = 500


def first_user_bodies(db_path, session_ids, limit=40) -> dict[str, str]:
    # Batched equivalent of "first message whose type contains 'user' (any case) among
    # session_messages(db_path, sid, limit)", over one connection. Every requested id gets a
    # key; ids with no such message (or not in the DB) map to "". Bodies are fetched only for
    # user-typed messages, since assistant bodies are large and never wanted.
    session_ids = list(session_ids)
    out = {sid: "" for sid in session_ids}
    conn = _connect(db_path)
    try:
        for i in range(0, len(session_ids), _SQLITE_VARIABLE_CHUNK):
            chunk = session_ids[i:i + _SQLITE_VARIABLE_CHUNK]
            marks = ",".join("?" * len(chunk))
            windowed = conn.execute(
                "SELECT session_id, id, type FROM ("
                "SELECT s.session_id AS session_id, m.id AS id, m.type AS type, "
                "ROW_NUMBER() OVER (PARTITION BY m.session_id ORDER BY m.sequence) AS n "
                "FROM messages m JOIN sessions s ON s.id = m.session_id "
                f"WHERE s.session_id IN ({marks}) "
                "AND (m.is_sidechain IS NULL OR m.is_sidechain=0)"
                ") WHERE n <= ? ORDER BY session_id, n",
                (*chunk, limit),
            ).fetchall()
            user_rows = [(r["session_id"], r["id"]) for r in windowed if "user" in (r["type"] or "").lower()]
            for j in range(0, len(user_rows), _SQLITE_VARIABLE_CHUNK):
                part = user_rows[j:j + _SQLITE_VARIABLE_CHUNK]
                bodies = dict(conn.execute(
                    "SELECT id, COALESCE(NULLIF(text_content,''), content) FROM messages "
                    f"WHERE id IN ({','.join('?' * len(part))})",
                    [message_id for _, message_id in part],
                ))
                for sid, message_id in part:
                    body = (bodies[message_id] or "").strip()
                    if body and not out[sid]:
                        out[sid] = body
    finally:
        conn.close()
    return out
