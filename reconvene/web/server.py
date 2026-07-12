# ABOUTME: Local HTTP server for Reconvene — a small JSON API plus static file serving.
# ABOUTME: Bound to 127.0.0.1 only; never exposed to the network.
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from ..db import load_sessions
from ..journal import build_journal
from ..recap import first_user_message

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _project_summary(p, db_path):
    return {
        "name": p.name,
        "category": p.category,
        "count": p.count,
        "last_active": p.last_active,
        "latest_session_id": p.latest.session_id,
        "oneline": first_user_message(db_path, p.latest.session_id) or "(no recap)",
    }


def make_handler(config, db_path, cache_path, resumer):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass  # keep test/CLI output quiet

        def _send_json(self, status, payload):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_static(self, rel_path):
            file_path = (STATIC_DIR / rel_path).resolve()
            try:
                file_path.relative_to(STATIC_DIR.resolve())
            except ValueError:
                self.send_response(404)
                self.end_headers()
                return
            if not file_path.is_file():
                self.send_response(404)
                self.end_headers()
                return
            content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
            body = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/api/journal":
                sessions = load_sessions(db_path)
                real, bots = build_journal(sessions, config)
                self._send_json(200, {
                    "real": [_project_summary(p, db_path) for p in real],
                    "bots": [_project_summary(p, db_path) for p in bots],
                })
                return
            rel_path = "index.html" if path == "/" else path.lstrip("/")
            self._send_static(rel_path)

        def do_POST(self):
            path = urlparse(self.path).path
            if path.startswith("/api/resume/"):
                session_id = path[len("/api/resume/"):]
                sessions = load_sessions(db_path)
                real, bots = build_journal(sessions, config)
                match = next(
                    (s for p in real + bots for s in p.sessions if s.session_id == session_id),
                    None,
                )
                if match is None:
                    self._send_json(404, {"error": f"no session {session_id!r}"})
                    return
                try:
                    resumer(session_id, match.project_path)
                except Exception as e:
                    self._send_json(500, {"error": str(e)})
                    return
                self._send_json(200, {"status": "resumed"})
                return
            self.send_response(404)
            self.end_headers()

    return Handler


def serve(config, db_path, cache_path, resumer, host="127.0.0.1", port=0):
    handler = make_handler(config, db_path, cache_path, resumer)
    return ThreadingHTTPServer((host, port), handler)
