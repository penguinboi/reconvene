# ABOUTME: Rolls classified sessions into ranked per-project journal entries.
# ABOUTME: Real projects and bot projects are returned as two separately-sorted lists.
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .classify import classify_category, canonical_name
from .cluster import FALLBACK_SUFFIX, detect_roots
from .constants import NOISE_MESSAGE_FLOOR
from .db import Session


@dataclass
class Project:
    name: str
    category: str
    sessions: list[Session]
    kind: str = "project"  # "project" | "topic" (LLM-assigned group) | "loose" (unorganized root launches)

    @property
    def latest(self) -> Session:
        return self.sessions[0]

    @property
    def count(self) -> int:
        return len(self.sessions)

    @property
    def last_active(self) -> str:
        return self.latest.updated_at


def _age_seconds(last_active: str, now: datetime | None = None) -> float:
    # ccrider's real timestamps are UTC and carry fractional seconds plus a "+0000 UTC"
    # suffix (Go's default time.Time.String() format); only the leading "YYYY-MM-DD HH:MM:SS"
    # is fixed-width and parsed, so both that format and the simpler one used by tests work.
    # `now` defaults to naive-UTC to match ccrider's UTC timestamps (a local default would
    # misjudge age by the local UTC offset).
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    updated = datetime.strptime(last_active[:19], "%Y-%m-%d %H:%M:%S")
    return (now - updated).total_seconds()


def recency_bucket(last_active: str, now: datetime | None = None) -> str:
    delta = _age_seconds(last_active, now)
    if delta <= 24 * 3600:
        return "active"
    if delta <= 7 * 24 * 3600:
        return "recent"
    return "stale"


def relative_time(last_active: str, now: datetime | None = None) -> str:
    delta = _age_seconds(last_active, now)
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{int(delta // 60)}m ago"
    if delta < 86400:
        return f"{int(delta // 3600)}h ago"
    if delta < 30 * 86400:
        return f"{int(delta // 86400)}d ago"
    if delta < 365 * 86400:
        return f"{int(delta // (30 * 86400))}mo ago"
    return f"{int(delta // (365 * 86400))}y ago"


def verbose_age(last_active: str, now: datetime | None = None) -> str:
    delta = _age_seconds(last_active, now)
    if delta < 60:
        return "just now"
    if delta < 3600:
        n = int(delta // 60)
        return f"{n} minute{'s' if n != 1 else ''} ago"
    if delta < 24 * 3600:
        n = int(delta // 3600)
        return f"{n} hour{'s' if n != 1 else ''} ago"
    days = int(delta // (24 * 3600))
    if days < 7:
        return f"{days} day{'s' if days != 1 else ''} ago"
    if days < 30:
        n = days // 7
        return f"{n} week{'s' if n != 1 else ''} ago"
    if days < 365:
        n = days // 30
        return f"{n} month{'s' if n != 1 else ''} ago"
    n = days // 365
    return f"{n} year{'s' if n != 1 else ''} ago"


def abbreviate_home(path: str, home: str | None = None) -> str:
    home = home if home is not None else str(Path.home())
    if path == home:
        return "~"
    if path.startswith(home + "/"):
        return "~" + path[len(home):]
    return path


def _group_projects(sessions, config, topic_lookup=None):
    # Group sessions into Projects keyed by (category, canonical name). Noise-dropped sessions are
    # excluded; user-hidden ("hidden") ones are kept so the settings view can surface them.
    # Sessions launched from a root directory (one that path-prefixes >=3 real project paths, e.g.
    # bare ~/Code) don't belong to a nameable project: they group by cached topic assignment, or
    # fall back to one visibly-generic "<root> (loose sessions)" group per root.
    topic_lookup = topic_lookup or {}
    roots = detect_roots({s.project_path for s in sessions})
    hidden_lower = {n.lower() for n in config.hidden_names}
    groups: dict[tuple, list[Session]] = {}
    for s in sessions:
        if s.project_path.rstrip("/") in roots:
            if s.message_count <= NOISE_MESSAGE_FLOOR:
                continue
            topic = topic_lookup.get(s.session_id)
            if topic:
                name, kind = topic, "topic"
            else:
                name, kind = abbreviate_home(s.project_path.rstrip("/")) + FALLBACK_SUFFIX, "loose"
            cat = "hidden" if name.lower() in hidden_lower else "real"
            groups.setdefault((cat, name, kind), []).append(s)
            continue
        cat = classify_category(s.project_path, config, s.message_count)
        if cat == "drop":
            continue
        groups.setdefault((cat, canonical_name(s.project_path), "project"), []).append(s)
    projects = []
    for (cat, name, kind), sess in groups.items():
        sess.sort(key=lambda s: s.updated_at, reverse=True)
        projects.append(Project(name=name, category=cat, sessions=sess, kind=kind))
    return projects


def _by_recency(projects, category):
    return sorted((p for p in projects if p.category == category),
                  key=lambda p: p.last_active, reverse=True)


def build_journal(sessions, config, topic_lookup=None):
    projects = _group_projects(sessions, config, topic_lookup)
    return _by_recency(projects, "real"), _by_recency(projects, "bot")


def build_settings_projects(sessions, config, topic_lookup=None):
    # Real + bot + user-hidden projects, for the settings table -- so a hidden project stays visible
    # there (as a "Hidden" row) and can be toggled back. Noise-dropped projects remain excluded.
    projects = _group_projects(sessions, config, topic_lookup)
    return _by_recency(projects, "real") + _by_recency(projects, "bot") + _by_recency(projects, "hidden")
