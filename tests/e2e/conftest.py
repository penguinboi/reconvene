# ABOUTME: Fixtures starting a real Reconvene server for Playwright-driven E2E tests.
# ABOUTME: Each test gets its own isolated server, temp DB, and temp config — no shared state.
import threading

import pytest

from reconvene.config import Config, save_config
from reconvene.web.server import serve


def _start_server(tmp_path, ccrider_db, resumer):
    config_path = tmp_path / "config.json"
    config = Config()
    save_config(config, config_path)

    def fake_recap_runner(prompt):
        return "ONELINE: full recap text\nDETAIL: full recap text"

    server = serve(
        config, str(ccrider_db), str(tmp_path / "recaps.db"), str(config_path),
        resumer, recap_runner=fake_recap_runner, port=0,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    return server, base_url, config, config_path


@pytest.fixture
def e2e_server(tmp_path, ccrider_db):
    resumed = []

    def fake_resumer(session_id, cwd):
        resumed.append((session_id, cwd))

    server, base_url, config, config_path = _start_server(tmp_path, ccrider_db, fake_resumer)
    yield base_url, resumed, config, config_path
    server.shutdown()
    server.server_close()


@pytest.fixture
def e2e_server_failing_resume(tmp_path, ccrider_db):
    resumed = []

    def failing_resumer(session_id, cwd):
        raise RuntimeError("could not open Terminal")

    server, base_url, config, config_path = _start_server(tmp_path, ccrider_db, failing_resumer)
    yield base_url, resumed, config, config_path
    server.shutdown()
    server.server_close()
