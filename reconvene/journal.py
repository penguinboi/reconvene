# ABOUTME: Rolls classified sessions into ranked per-project journal entries.
# ABOUTME: Real projects and bot projects are returned as two separately-sorted lists.
from dataclasses import dataclass

from .classify import classify_category, canonical_name
from .db import Session


@dataclass
class Project:
    name: str
    category: str
    sessions: list[Session]

    @property
    def latest(self) -> Session:
        return self.sessions[0]

    @property
    def count(self) -> int:
        return len(self.sessions)

    @property
    def last_active(self) -> str:
        return self.latest.updated_at


def build_journal(sessions, config):
    groups: dict[tuple[str, str], list[Session]] = {}
    for s in sessions:
        cat = classify_category(s.project_path, config, s.message_count)
        if cat == "drop":
            continue
        groups.setdefault((cat, canonical_name(s.project_path)), []).append(s)
    projects = []
    for (cat, name), sess in groups.items():
        sess.sort(key=lambda s: s.updated_at, reverse=True)
        projects.append(Project(name=name, category=cat, sessions=sess))
    real = sorted((p for p in projects if p.category == "real"),
                  key=lambda p: p.last_active, reverse=True)
    bots = sorted((p for p in projects if p.category == "bot"),
                  key=lambda p: p.last_active, reverse=True)
    return real, bots
