# ABOUTME: Terminal frontend — an fzf picker over the ranked journal that hands off to claude --resume.
# ABOUTME: Recaps load lazily per highlighted item via an fzf --preview command (reconvene._preview).
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from .db import load_sessions
from .journal import abbreviate_home, build_journal, relative_time
from .recap import first_user_message
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


def _preview_command(db_path, cache_path, config_path, session=False) -> str:
    # fzf substitutes {1} with the highlighted row's hidden session-id column, then runs this per
    # item and streams its stdout into the preview pane. sys.executable keeps us on the same
    # interpreter as the running TUI. PYTHONPATH points the child at the package root so
    # `-m reconvene._preview` imports even under a bare `bin/reconvene` symlink install (whose
    # runtime sys.path insert a subprocess would not inherit); harmless under a pip/pipx install.
    pkg_root = str(Path(__file__).resolve().parent.parent)
    cmd = (
        f"PYTHONPATH={shlex.quote(pkg_root)} {shlex.quote(sys.executable)} "
        f"-m reconvene._preview {{1}} "
        f"{shlex.quote(db_path)} {shlex.quote(cache_path)} {shlex.quote(config_path)}"
    )
    return cmd + " --session" if session else cmd


def render_session_line(session, db_path) -> str:
    first = first_user_message(db_path, session.session_id, limit=70)
    return (f"{session.session_id}\t{relative_time(session.updated_at)}"
            f" · {session.message_count} msgs · {first}")


def _make_fzf_picker(preview_cmd, expect=()):
    # Returns (key, chosen_line). key is "" for a plain enter; with --expect, fzf prints the
    # pressed key on the first output line and the highlighted line on the second. esc/abort
    # yields ("", None).
    def picker(lines):
        cmd = ["fzf", "--no-sort", "--layout=reverse", "--border=rounded", "--info=inline",
               "--delimiter", "\t", "--with-nth", "2..",
               "--preview", preview_cmd,
               "--preview-window", "right:65%:wrap"]
        if expect:
            cmd += ["--expect", ",".join(expect)]
        proc = subprocess.run(cmd, input="\n".join(lines), capture_output=True, text=True)
        out = proc.stdout.splitlines()
        if not expect:
            return ("", out[0] if out and out[0] else None)
        if not out:
            return ("", None)
        key = out[0].strip()
        chosen = out[1] if len(out) > 1 and out[1] else None
        return (key, chosen)
    return picker


def run_tui(config, db_path, cache_path, config_path, show_bots=False, *,
            picker=None, session_picker=None, resumer=exec_resume) -> int:
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
    project_picker = picker or _make_fzf_picker(
        _preview_command(db_path, cache_path, config_path), expect=("ctrl-s",))
    active_session_picker = session_picker or _make_fzf_picker(
        _preview_command(db_path, cache_path, config_path, session=True))

    while True:
        key, chosen = project_picker(lines)
        if not chosen and key != "ctrl-s":
            return 0
        project = sid_to_project.get(chosen.split("\t", 1)[0]) if chosen else None
        if project is None:
            if key == "ctrl-s":
                continue  # ctrl-s on a separator/empty line: just re-show the list
            return 0      # separator picked with enter
        if key == "ctrl-s":
            session_lines = [render_session_line(s, db_path) for s in project.sessions]
            _, s_chosen = active_session_picker(session_lines)
            if not s_chosen:
                continue  # esc: back to the project list
            sid = s_chosen.split("\t", 1)[0]
            session = next((s for s in project.sessions if s.session_id == sid), None)
            if session is None:
                continue
            resumer(session.session_id, session.project_path, session.updated_at, config)
            return 0
        resumer(project.latest.session_id, project.latest.project_path,
                project.latest.updated_at, config)
        return 0
