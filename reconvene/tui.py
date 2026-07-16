# ABOUTME: Terminal frontend — an fzf picker over the ranked journal that hands off to claude --resume.
# ABOUTME: Mirrors the web GUI's data flow (journal + recaps) but resumes via execvp in the foreground.
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .db import load_sessions
from .journal import abbreviate_home, build_journal, relative_time
from .recap import RecapCache, ensure_recaps
from .resume import exec_resume

SEPARATOR_SID = ""


def render_line(project) -> str:
    return f"{project.name} · {relative_time(project.last_active)} · {project.count} sessions"


def render_preview(project, full) -> str:
    latest = project.latest
    stats = "\n".join([
        project.name,
        f"{project.count} sessions · last {relative_time(project.last_active)}",
        f"path  {abbreviate_home(latest.project_path)}",
    ])
    return f"{stats}\n{'─' * 46}\n\n{full}"


def build_entries(real, bots, show_bots):
    entries = [(render_line(p), p.latest.session_id) for p in real]
    if show_bots and bots:
        entries.append(("──────── automated ────────", SEPARATOR_SID))
        entries.extend((render_line(p), p.latest.session_id) for p in bots)
    return entries


def _make_fzf_picker(tmpdir):
    def picker(lines):
        proc = subprocess.run(
            ["fzf", "--no-sort", "--layout=reverse", "--border=rounded", "--info=inline",
             "--delimiter", "\t", "--with-nth", "2..",
             "--preview", "cat " + shlex.quote(tmpdir) + "/{1} 2>/dev/null",
             "--preview-window", "right:65%:wrap"],
            input="\n".join(lines), capture_output=True, text=True,
        )
        out = proc.stdout.strip()
        return out or None
    return picker


def run_tui(config, db_path, cache_path, show_bots=False, *, picker=None, resumer=exec_resume) -> int:
    if picker is None and shutil.which("fzf") is None:
        print("reconvene: the terminal picker needs fzf — install it with: brew install fzf",
              file=sys.stderr)
        return 1

    sessions = load_sessions(db_path)
    real, bots = build_journal(sessions, config)
    shown = real + (bots if show_bots else [])
    if not shown:
        if bots:  # bots exist but are hidden without --bots
            print("No projects to show. Use -b to include automated-runs projects.", file=sys.stderr)
        else:
            print("No projects found.", file=sys.stderr)
        return 1

    cache = RecapCache(cache_path)
    try:
        recaps = ensure_recaps(shown, db_path, cache, config)
    finally:
        cache.close()

    tmpdir = tempfile.mkdtemp(prefix="reconvene-")
    try:
        for p in shown:
            full = recaps.get(p.name, ("", "(no recap)"))[1]
            Path(tmpdir, p.latest.session_id).write_text(render_preview(p, full))
        entries = build_entries(real, bots, show_bots)
        sid_to_project = {p.latest.session_id: p for p in shown}
        lines = [f"{sid}\t{display}" for display, sid in entries]
        active_picker = picker or _make_fzf_picker(tmpdir)
        chosen = active_picker(lines)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    if not chosen:
        return 0
    sid = chosen.split("\t", 1)[0]
    project = sid_to_project.get(sid)
    if project is None:
        return 0  # separator or unrecognized line
    resumer(sid, project.latest.project_path, project.latest.updated_at, config)
    return 0
