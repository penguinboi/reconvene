# ABOUTME: CLI entry point — a startup chooser dispatches to the web GUI or the terminal picker.
# ABOUTME: Both frontends share ccrider sync and the same flags (--db/--cache/--config/--no-sync).
import argparse
import socket
import subprocess
import sys
import threading
import webbrowser

from .config import load_config
from .constants import CCRIDER_DB, CONFIG_PATH, RECAP_CACHE_DB, VERSION
from .resume import open_terminal_and_resume
from .tui import run_tui
from .web.server import serve


def find_free_port(preferred=4242, tries=10) -> int:
    for offset in range(tries):
        candidate = preferred + offset
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("127.0.0.1", candidate))
            return candidate
        except OSError:
            continue
        finally:
            sock.close()
    raise RuntimeError(f"no free port found in range {preferred}-{preferred + tries - 1}")


def _choose_frontend(input_fn=input) -> str | None:
    print("Reconvene — a Penguinboi Software tool")
    print("  [1] Web view")
    print("  [2] TUI")
    while True:
        try:
            choice = input_fn("> ").strip()
        except EOFError:
            return None
        if choice == "1":
            return "web"
        if choice == "2":
            return "tui"
        print("Please enter 1 or 2.", file=sys.stderr)


def _serve_web(config, db, cache, config_path) -> int:
    try:
        port = find_free_port()
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    resumer = lambda session_id, cwd, updated_at: open_terminal_and_resume(session_id, cwd, updated_at, config)
    server = serve(config, db, cache, config_path, resumer, port=port)
    url = f"http://127.0.0.1:{port}"
    print(f"Reconvene running at {url}")
    threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def main(argv=None, *, input_fn=input, stdin_isatty=None,
         launch_web=None, launch_tui=None) -> int:
    ap = argparse.ArgumentParser(prog="reconvene", description="Resume a Claude Code project by its journal.")
    ap.add_argument("--no-sync", action="store_true", help="skip `ccrider sync` first")
    ap.add_argument("-b", "--bots", action="store_true", help="TUI: include the automated-runs section")
    ap.add_argument("--db", default=str(CCRIDER_DB), help="ccrider sessions DB path")
    ap.add_argument("--cache", default=str(RECAP_CACHE_DB), help="recap cache path")
    ap.add_argument("--config", default=str(CONFIG_PATH), help="config file path")
    ap.add_argument("-s", "--search", nargs="?", const="", default=None, metavar="QUERY",
                    help="open the TUI directly in search mode (optional initial query)")
    ap.add_argument("--organize", action="store_true",
                    help="cluster loose (root-launched) sessions into topics and exit")
    ap.add_argument("-V", "--version", action="version", version=f"reconvene {VERSION}")
    args = ap.parse_args(argv)

    if not args.no_sync and args.db == str(CCRIDER_DB):
        try:
            result = subprocess.run(["ccrider", "sync"])
        except FileNotFoundError:
            print(
                "error: `ccrider` isn't installed or isn't on PATH.\n"
                "Install it with: brew install neilberkman/tap/ccrider",
                file=sys.stderr,
            )
            return 1
        if result.returncode != 0:
            print(f"warning: `ccrider sync` exited {result.returncode}; showing possibly-stale data", file=sys.stderr)

    config = load_config(args.config)

    if args.organize:
        from .cluster import TopicAuthError, TopicCache, organize, unassigned_loose_sessions
        from .db import load_sessions
        sessions = load_sessions(args.db)
        cache = TopicCache(args.cache)
        try:
            unassigned = unassigned_loose_sessions(sessions, cache.get_all())
            try:
                n = organize(unassigned, args.db, cache, config, runner=None)
            except TopicAuthError as e:
                print(f"error: {e}", file=sys.stderr)
                return 1
            except Exception as e:
                print(f"error: clustering failed: {e}", file=sys.stderr)
                return 1
            lookup = cache.get_all()
        finally:
            cache.close()
        by_topic: dict[str, int] = {}
        for s in unassigned:
            topic = lookup.get(s.session_id)
            if topic:
                by_topic[topic] = by_topic.get(topic, 0) + 1
        print(f"assigned {n} session{'s' if n != 1 else ''}")
        for topic, count in sorted(by_topic.items()):
            print(f"  {topic}: {count}")
        return 0

    interactive = sys.stdin.isatty() if stdin_isatty is None else stdin_isatty
    if args.search is not None:
        mode = "tui"
    else:
        mode = _choose_frontend(input_fn) if interactive else "web"
    if mode is None:
        return 0  # user cancelled the chooser

    if mode == "tui":
        return (launch_tui or run_tui)(config, args.db, args.cache, args.config, args.bots,
                                        initial_search=args.search)
    return (launch_web or _serve_web)(config, args.db, args.cache, args.config)
