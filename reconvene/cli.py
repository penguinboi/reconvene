# ABOUTME: CLI entry point — syncs ccrider, starts the local web server, opens the browser.
import argparse
import socket
import subprocess
import sys
import threading
import webbrowser

from .config import load_config
from .constants import CCRIDER_DB, CONFIG_PATH, RECAP_CACHE_DB, VERSION
from .resume import open_terminal_and_resume
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="reconvene", description="Resume a Claude Code project by its journal.")
    ap.add_argument("--no-sync", action="store_true", help="skip `ccrider sync` first")
    ap.add_argument("--db", default=str(CCRIDER_DB), help="ccrider sessions DB path")
    ap.add_argument("--cache", default=str(RECAP_CACHE_DB), help="recap cache path")
    ap.add_argument("--config", default=str(CONFIG_PATH), help="config file path")
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
    try:
        port = find_free_port()
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    resumer = lambda session_id, cwd, updated_at: open_terminal_and_resume(session_id, cwd, updated_at, config)
    server = serve(config, args.db, args.cache, args.config, resumer, port=port)
    url = f"http://127.0.0.1:{port}"
    print(f"Reconvene running at {url}")
    threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0
