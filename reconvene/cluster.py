# ABOUTME: Root-launch detection and sticky topic assignments for "loose" sessions.
# ABOUTME: A root = a session path that path-prefixes >=3 other session paths (worktrees excluded).
import sqlite3
from pathlib import Path

from .constants import WORKTREE_MARKERS

FALLBACK_SUFFIX = " (loose sessions)"


def detect_roots(paths) -> set[str]:
    norm = {p.rstrip("/") for p in paths if p and p.rstrip("/")}
    roots = set()
    for cand in norm:
        prefix = cand + "/"
        children = {
            p for p in norm
            if p != cand and p.startswith(prefix)
            and not any(m in p[len(cand):] for m in WORKTREE_MARKERS)
        }
        if len(children) >= 3:
            roots.add(cand)
    return roots


class TopicCache:
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS topic_assignments "
            "(session_id TEXT PRIMARY KEY, topic TEXT NOT NULL)"
        )
        self.conn.commit()

    def get_all(self) -> dict[str, str]:
        return dict(self.conn.execute("SELECT session_id, topic FROM topic_assignments"))

    def assign(self, session_id, topic):
        # OR IGNORE = stickiness: an existing assignment is never overwritten.
        self.conn.execute(
            "INSERT OR IGNORE INTO topic_assignments(session_id, topic) VALUES (?, ?)",
            (session_id, topic),
        )
        self.conn.commit()

    def topics(self) -> set[str]:
        return {t for (t,) in self.conn.execute("SELECT DISTINCT topic FROM topic_assignments")}

    def close(self):
        self.conn.close()


def load_topic_lookup(cache_path) -> dict[str, str]:
    cache = TopicCache(cache_path)
    try:
        return cache.get_all()
    finally:
        cache.close()
