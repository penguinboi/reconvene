# ABOUTME: fzf --preview target — prints one project's stats header + recap on demand.
# ABOUTME: Cache-first; generates (via claude) only on a miss, so the TUI never blocks up front.
import sys

from .classify import canonical_name
from .config import load_config
from .constants import RECENT_SESSIONS_FOR_RECAP
from .db import load_sessions
from .journal import abbreviate_home, build_journal, relative_time
from .recap import RecapCache, ensure_recaps, first_user_message, signature
from .tui import render_header


def _find_project(config, db_path, session_id):
    real, bots = build_journal(load_sessions(db_path), config)
    return next((p for p in real + bots if p.latest.session_id == session_id), None)


def _print_recap(project, db_path, cache_path, config, recaps_fn):
    # Cache-first. On a miss, generate inline (blocking just this one preview) and print the recap.
    # No streamed "generating…" placeholder: fzf's preview pane appends stdout as it arrives and does
    # not honor in-place line-clears (\r, \033[2K), so any placeholder would linger above the finished
    # recap. The header — already flushed by the caller — stays visible during generation, so the pane
    # is never blank; it just fills in below once the recap is ready.
    cache = RecapCache(cache_path)
    try:
        sig = signature(project.sessions[:RECENT_SESSIONS_FOR_RECAP])
        hit = cache.get(project.name, sig)
        if hit is not None:
            print(hit[1])
            return
        try:
            result = recaps_fn([project], db_path, cache, config)
            body = result.get(project.name, ("", "(no recap)"))[1]
        except Exception as e:
            body = f"⚠ recap unavailable: {e}"
        print(body)
    finally:
        cache.close()


def _print_session_detail(session, db_path):
    print(canonical_name(session.project_path))
    print(f"session {session.session_id[:8]} · {relative_time(session.updated_at)}"
          f" · {session.message_count} messages")
    print(f"path  {abbreviate_home(session.project_path)}")
    print("─" * 46)
    print()
    print(first_user_message(db_path, session.session_id, limit=400) or "(no messages)")
    if session.summary:
        print()
        print(session.summary)


def main(argv, *, recaps_fn=ensure_recaps) -> int:
    session_mode = "--session" in argv
    argv = [a for a in argv if a != "--session"]
    session_id, db_path, cache_path, config_path = argv[0], argv[1], argv[2], argv[3]
    try:
        config = load_config(config_path)
        if session_mode:
            session = next((s for s in load_sessions(db_path) if s.session_id == session_id), None)
            if session is None:
                print("(session not found)")
                return 0
            _print_session_detail(session, db_path)
            return 0
        project = _find_project(config, db_path, session_id)
    except Exception as e:
        # Bad db/config path etc. — never dump a traceback into the preview pane.
        print(f"⚠ recap unavailable: {e}")
        return 0
    if project is None:
        print("(project not found)")
        return 0
    print(render_header(project), flush=True)
    print()  # blank line between header and body
    try:
        _print_recap(project, db_path, cache_path, config, recaps_fn)
    except Exception as e:
        print(f"⚠ recap unavailable: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
