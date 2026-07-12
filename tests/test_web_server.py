# ABOUTME: Tests for the local HTTP server — routes tested via real HTTP requests
# ABOUTME: against a server instance running on a random free port in a background thread.
import json
import threading
import urllib.request
from urllib.error import HTTPError

import pytest

from reconvene.config import Config
from reconvene.web.server import serve
from tests.conftest import add_session, add_message


@pytest.fixture
def running_server(tmp_path, ccrider_db):
    add_session(ccrider_db, "r1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "r1", "user", "wire up thresholds", sequence=1)
    config = Config()
    resumed = []
    def fake_resumer(session_id, cwd):
        resumed.append((session_id, cwd))
    server = serve(config, str(ccrider_db), str(tmp_path / "recaps.db"), fake_resumer, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    yield base_url, resumed, config
    server.shutdown()
    server.server_close()


def test_index_serves_static_html(running_server):
    base_url, _, _ = running_server
    with urllib.request.urlopen(f"{base_url}/") as resp:
        assert resp.status == 200
        assert b"Reconvene" in resp.read()


def test_unknown_static_path_is_404(running_server):
    base_url, _, _ = running_server
    with pytest.raises(HTTPError) as exc:
        urllib.request.urlopen(f"{base_url}/no-such-file.html")
    assert exc.value.code == 404


def test_static_path_traversal_is_blocked(running_server):
    base_url, _, _ = running_server
    with pytest.raises(HTTPError) as exc:
        urllib.request.urlopen(f"{base_url}/../../../etc/passwd")
    assert exc.value.code == 404


def test_api_journal_returns_ranked_projects(running_server):
    base_url, _, _ = running_server
    with urllib.request.urlopen(f"{base_url}/api/journal") as resp:
        data = json.loads(resp.read())
    assert data["real"][0]["name"] == "myproject"
    assert data["real"][0]["latest_session_id"] == "r1"
    assert "wire up thresholds" in data["real"][0]["oneline"]
    assert data["bots"] == []
