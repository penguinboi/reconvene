# ABOUTME: Root-launch detection and sticky topic assignments for "loose" sessions.
# ABOUTME: A root = a session path that path-prefixes >=3 other session paths (worktrees excluded).
import sqlite3
from pathlib import Path

from .constants import NOISE_MESSAGE_FLOOR, WORKTREE_MARKERS
from .recap import claude_runner, first_user_message

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


class TopicAuthError(RuntimeError):
    pass


ORGANIZE_PROMPT = (
    "You are organizing loose coding-assistant sessions (all launched from a generic root "
    "directory, not a project folder) into small named topic groups.\n\n"
    "Existing topics — reuse one when it fits:\n{existing}\n\n"
    "Sessions (id, date, first message, optional summary):\n{sessions}\n\n"
    "Respond with EXACTLY one line per session, in the format:\n"
    "<session_id>: <Topic Name>\n"
    "Topic names are 2-4 words, Title Case. Output nothing else."
)


def build_organize_prompt(unassigned, db_path, existing_topics) -> str:
    blocks = []
    for s in unassigned:
        first = first_user_message(db_path, s.session_id, limit=200)
        line = f"- {s.session_id} ({s.updated_at[:10]}): {first}"
        summary = (s.summary or "").replace("\n", " ").strip()
        if summary:
            line += f" | summary: {summary[:200]}"
        blocks.append(line)
    existing = "\n".join(f"- {t}" for t in sorted(existing_topics)) or "(none yet)"
    return ORGANIZE_PROMPT.format(existing=existing, sessions="\n".join(blocks))


def parse_assignments(output, valid_ids) -> dict[str, str]:
    out = {}
    for line in output.splitlines():
        sid, sep, topic = line.partition(":")
        sid, topic = sid.strip().lstrip("- ").strip(), topic.strip()
        if sep and topic and sid in valid_ids:
            out[sid] = topic
    return out


def organize(unassigned, db_path, cache, config, runner=None) -> int:
    # One claude call assigns every unassigned loose session to a topic. Existing cache rows are
    # never touched (assign is INSERT OR IGNORE). Returns how many sessions got assigned.
    if config.recap_auth_mode == "none":
        raise TopicAuthError(
            "topic clustering needs Claude — recap auth mode is 'none' (change it in Settings)"
        )
    if not unassigned:
        return 0
    run = runner or (lambda prompt: claude_runner(prompt, config))
    output = run(build_organize_prompt(unassigned, db_path, cache.topics()))
    assigned = parse_assignments(output, {s.session_id for s in unassigned})
    for sid, topic in assigned.items():
        cache.assign(sid, topic)
    return len(assigned)


def unassigned_loose_sessions(sessions, lookup):
    roots = detect_roots({s.project_path for s in sessions})
    return [
        s for s in sessions
        if s.project_path.rstrip("/") in roots
        and s.session_id not in lookup
        and s.message_count > NOISE_MESSAGE_FLOOR
    ]
