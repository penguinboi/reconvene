# ABOUTME: fzf --preview target — prints a project's (or, with --session, one session's) header + recap.
# ABOUTME: Cache-first; generates (via claude) only on a miss, so the TUI never blocks up front.
import sys

from .classify import canonical_name
from .config import load_config
from .constants import RECENT_SESSIONS_FOR_RECAP
from .db import load_sessions
from .journal import abbreviate_home, build_journal, relative_time
from .recap import SESSION_CACHE_PREFIX, RecapCache, ensure_recaps, ensure_session_recap, signature
from .tui import render_header


def _find_project(config, db_path, cache_path, session_id):
    from .cluster import load_topic_lookup
    real, bots = build_journal(load_sessions(db_path), config,
                               topic_lookup=load_topic_lookup(cache_path))
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


def _render_session_header(session) -> str:
    return "\n".join([
        canonical_name(session.project_path),
        f"session {session.session_id[:8]} · {relative_time(session.updated_at)}"
        f" · {session.message_count} messages",
        f"path  {abbreviate_home(session.project_path)}",
        "─" * 46,
    ])


BUILDING_NOTE = "⏳ building summary — one moment (instant after the first open)"


def _print_session(session, db_path, cache_path, config, session_recaps_fn):
    # Header first (flushed) so it shows immediately while a recap generates. On an uncached session
    # that will actually call claude, a one-line note warns about the first-open wait. It can't be a
    # disappearing spinner — fzf's preview pane is append-only and can't erase it — so it's phrased as
    # context and shown ONLY on the generating open; cached opens (and 'none' auth, which derives
    # instantly) print the header + recap with no note.
    cache = RecapCache(cache_path)
    try:
        cached = cache.get(SESSION_CACHE_PREFIX + session.session_id, signature([session])) is not None
        print(_render_session_header(session), flush=True)
        print()  # blank line between header and body
        if not cached and config.recap_auth_mode != "none":
            print(BUILDING_NOTE, flush=True)
        try:
            _, body = session_recaps_fn(session, db_path, cache, config)
        except Exception as e:
            body = f"⚠ recap unavailable: {e}"
        print(body)
    finally:
        cache.close()


def main(argv, *, recaps_fn=ensure_recaps, session_recaps_fn=ensure_session_recap) -> int:
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
            _print_session(session, db_path, cache_path, config, session_recaps_fn)
            return 0
        project = _find_project(config, db_path, cache_path, session_id)
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
