# ABOUTME: Full-text session search over ccrider's messages_fts FTS5 index (read-only).
# ABOUTME: Sanitizes queries into quoted-token AND form so FTS5 syntax errors are impossible.
import sqlite3
from dataclasses import dataclass

from .db import _connect

SNIPPET_OPEN = "«"
SNIPPET_CLOSE = "»"


@dataclass(frozen=True)
class SearchHit:
    session_id: str
    project_path: str
    updated_at: str
    message_count: int
    hits: int
    snippet: str


def sanitize_query(query: str) -> str:
    # Each whitespace token becomes a quoted FTS5 string ("pi-hole" "nas" = implicit AND).
    # Quoting disables all FTS5 operator syntax, so user input can never cause a parse error;
    # porter stemming still applies inside quoted strings.
    tokens = [t.replace('"', "") for t in query.split()]
    return " ".join(f'"{t}"' for t in tokens if t)


def search_sessions(db_path, query, limit=30) -> list[SearchHit]:
    match = sanitize_query(query)
    if not match:
        return []
    conn = _connect(db_path)
    try:
        try:
            counts = conn.execute(
                "SELECT s.session_id, s.project_path, s.updated_at, s.message_count, "
                "count(*) AS hits, min(messages_fts.rowid) AS first_rowid "
                "FROM messages_fts "
                "JOIN messages m ON m.id = messages_fts.rowid "
                "JOIN sessions s ON s.id = m.session_id "
                "WHERE messages_fts MATCH ? "
                "GROUP BY s.id ORDER BY hits DESC, s.updated_at DESC LIMIT ?",
                (match, limit),
            ).fetchall()
            hits = []
            for r in counts:
                (snip,) = conn.execute(
                    "SELECT snippet(messages_fts, 0, ?, ?, '…', 10) "
                    "FROM messages_fts WHERE messages_fts MATCH ? AND rowid = ?",
                    (SNIPPET_OPEN, SNIPPET_CLOSE, match, r["first_rowid"]),
                ).fetchone()
                hits.append(SearchHit(
                    r["session_id"], r["project_path"], r["updated_at"],
                    r["message_count"] or 0, r["hits"], snip,
                ))
        except sqlite3.OperationalError as e:
            if "messages_fts" in str(e):
                raise RuntimeError(
                    "ccrider database has no messages_fts full-text index — "
                    "run `ccrider sync`, or ccrider's schema changed"
                ) from e
            raise
    finally:
        conn.close()
    return hits
