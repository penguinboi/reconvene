# ABOUTME: Terminal frontend — an fzf picker over the ranked journal that hands off to claude --resume.
# ABOUTME: Recaps load lazily per highlighted item via an fzf --preview command (reconvene._preview).
import shlex
import shutil
import subprocess
import sys

from .db import load_sessions
from .journal import abbreviate_home, build_journal, relative_time
from .resume import exec_resume

SEPARATOR_SID = ""


def render_line(project) -> str:
    return f"{project.name} · {relative_time(project.last_active)} · {project.count} sessions"


def render_header(project) -> str:
    latest = project.latest
    return "\n".join([
        project.name,
        f"{project.count} sessions · last {relative_time(project.last_active)}",
        f"path  {abbreviate_home(latest.project_path)}",
        "─" * 46,
    ])


def build_entries(real, bots, show_bots):
    entries = [(render_line(p), p.latest.session_id) for p in real]
    if show_bots and bots:
        entries.append(("──────── automated ────────", SEPARATOR_SID))
        entries.extend((render_line(p), p.latest.session_id) for p in bots)
    return entries


def _preview_command(db_path, cache_path, config_path) -> str:
    # fzf substitutes {1} with the highlighted row's hidden session-id column, then runs this per
    # item and streams its stdout into the preview pane. sys.executable keeps us on the same
    # interpreter as the running TUI (robust under pipx/venv/system installs).
    return (
        f"{shlex.quote(sys.executable)} -m reconvene._preview {{1}} "
        f"{shlex.quote(db_path)} {shlex.quote(cache_path)} {shlex.quote(config_path)}"
    )


def _make_fzf_picker(preview_cmd):
    def picker(lines):
        proc = subprocess.run(
            ["fzf", "--no-sort", "--layout=reverse", "--border=rounded", "--info=inline",
             "--delimiter", "\t", "--with-nth", "2..",
             "--preview", preview_cmd,
             "--preview-window", "right:65%:wrap"],
            input="\n".join(lines), capture_output=True, text=True,
        )
        return proc.stdout.strip() or None
    return picker


def run_tui(config, db_path, cache_path, config_path, show_bots=False, *, picker=None, resumer=exec_resume) -> int:
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

    entries = build_entries(real, bots, show_bots)
    sid_to_project = {p.latest.session_id: p for p in shown}
    lines = [f"{sid}\t{display}" for display, sid in entries]
    active_picker = picker or _make_fzf_picker(_preview_command(db_path, cache_path, config_path))
    chosen = active_picker(lines)

    if not chosen:
        return 0
    sid = chosen.split("\t", 1)[0]
    project = sid_to_project.get(sid)
    if project is None:
        return 0  # separator or unrecognized line
    resumer(sid, project.latest.project_path, project.latest.updated_at, config)
    return 0
