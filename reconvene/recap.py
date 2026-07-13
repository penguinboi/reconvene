# ABOUTME: Generates and caches per-project recaps from recent session transcripts via `claude -p`.
# ABOUTME: Cache is keyed by project + a signature of the included sessions so grown sessions refresh.
import hashlib
import os
import sqlite3
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .constants import MODEL, RECAP_CACHE_DB, RECAP_CONCURRENCY, RECENT_SESSIONS_FOR_RECAP
from .db import session_messages


def signature(sessions) -> str:
    parts = [f"{s.session_id}:{s.updated_at}:{s.message_count}" for s in sessions]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


class RecapCache:
    def __init__(self, path=RECAP_CACHE_DB):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS recaps "
            "(project TEXT PRIMARY KEY, signature TEXT, oneline TEXT, full TEXT)"
        )
        self.conn.commit()

    def get(self, project, sig):
        row = self.conn.execute(
            "SELECT oneline, full FROM recaps WHERE project=? AND signature=?",
            (project, sig),
        ).fetchone()
        return (row[0], row[1]) if row else None

    def put(self, project, sig, oneline, full):
        self.conn.execute(
            "INSERT INTO recaps(project,signature,oneline,full) VALUES(?,?,?,?) "
            "ON CONFLICT(project) DO UPDATE SET "
            "signature=excluded.signature, oneline=excluded.oneline, full=excluded.full",
            (project, sig, oneline, full),
        )
        self.conn.commit()

    def close(self):
        self.conn.close()


PROMPT_TEMPLATE = (
    "You are summarizing recent coding-agent sessions for the project '{name}' so the developer "
    "can decide whether to resume this thread. The sessions are newest-first.\n\n"
    "Respond in EXACTLY this format and nothing else:\n"
    "ONELINE: <one sentence, <=90 chars, what the project is currently about / last worked on>\n"
    "DETAIL: <a detailed, multi-paragraph summary, up to 600 words across 3-6 paragraphs. "
    "Cover: what problem or feature was being worked on and why, the concrete changes and decisions "
    "made across these sessions, any bugs found and how they were fixed, the current state of the "
    "code, and a specific recommended next step. Write in full sentences, not clipped fragments.>\n\n"
    "{transcript}"
)


def build_prompt(project, db_path, recent=RECENT_SESSIONS_FOR_RECAP, per_session_chars=6000):
    blocks = []
    for s in project.sessions[:recent]:
        msgs = session_messages(db_path, s.session_id)
        text = "\n".join(f"{sender}: {body}" for sender, body in msgs)
        blocks.append(f"--- session {s.updated_at} ---\n{text[:per_session_chars]}")
    return PROMPT_TEMPLATE.format(name=project.name, transcript="\n\n".join(blocks))


def parse_recap(output: str) -> tuple[str, str]:
    oneline, detail = "", ""
    for line in output.splitlines():
        if line.startswith("ONELINE:"):
            oneline = line[len("ONELINE:"):].strip()
        elif line.startswith("DETAIL:"):
            detail = line[len("DETAIL:"):].strip()
        elif detail and line.strip():
            detail += "\n" + line.strip()
    if not oneline:
        first = next((l for l in output.splitlines() if l.strip()), "")
        oneline = first.strip()[:90]
    return oneline, (detail or oneline)


def first_user_message(db_path, session_id, limit=90) -> str:
    msgs = session_messages(db_path, session_id)
    first_user = next((body for sender, body in msgs if "user" in sender.lower()), "")
    return first_user.replace("\n", " ").strip()[:limit]


def derive_recap(project, db_path) -> tuple[str, str]:
    oneline = first_user_message(db_path, project.latest.session_id) or "(no recap)"
    return oneline, oneline


def claude_runner(prompt, config, model=MODEL, timeout=120) -> str:
    env = dict(os.environ)
    if config.recap_auth_mode == "api_key" and config.api_key:
        env["ANTHROPIC_API_KEY"] = config.api_key
    proc = subprocess.run(
        ["claude", "-p", "--model", model, prompt],
        capture_output=True, text=True, env=env, timeout=timeout,
        cwd=tempfile.gettempdir(),  # not the user's launch cwd — keeps this call out of their project history
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p failed: {proc.stderr.strip()[:200]}")
    return proc.stdout


def generate_recap(project, db_path, runner) -> tuple[str, str]:
    return parse_recap(runner(build_prompt(project, db_path)))


def ensure_recaps(projects, db_path, cache, config, runner=None, concurrency=RECAP_CONCURRENCY):
    use_llm = config.recap_auth_mode != "none"
    active_runner = runner or (lambda prompt: claude_runner(prompt, config))

    results: dict[str, tuple[str, str]] = {}
    todo = []
    for p in projects:
        sig = signature(p.sessions[:RECENT_SESSIONS_FOR_RECAP])
        hit = cache.get(p.name, sig)
        if hit:
            results[p.name] = hit
        else:
            todo.append((p, sig))

    def work(item):
        p, sig = item
        try:
            recap = generate_recap(p, db_path, active_runner) if use_llm else derive_recap(p, db_path)
        except Exception:
            try:
                recap = derive_recap(p, db_path)
            except Exception:
                recap = ("(recap failed)", "(recap failed)")
        return p.name, sig, recap

    if todo:
        with ThreadPoolExecutor(max_workers=concurrency) as ex:
            for name, sig, recap in ex.map(work, todo):
                cache.put(name, sig, recap[0], recap[1])
                results[name] = recap
    return results
