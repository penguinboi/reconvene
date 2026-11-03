# ABOUTME: Fixtures starting a real Reconvene server for Playwright-driven E2E tests.
# ABOUTME: Each test gets its own isolated server, temp DB, and temp config — no shared state.
import shutil
import threading

import pytest

from reconvene.config import Config, save_config
from reconvene.web.server import serve


def _start_server(tmp_path, ccrider_db, resumer, handoff=None, which=shutil.which):
    config_path = tmp_path / "config.json"
    config = Config()
    save_config(config, config_path)

    def fake_recap_runner(prompt):
        if "organizing loose" in prompt:
            return "loose1: Homelab Fixes"
        return "ONELINE: full recap text\nDETAIL: full recap text"

    server = serve(
        config, str(ccrider_db), str(tmp_path / "recaps.db"), str(config_path),
        resumer, recap_runner=fake_recap_runner, handoff=handoff, which=which, port=0,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    return server, base_url, config, config_path


@pytest.fixture
def e2e_server(tmp_path, ccrider_db):
    resumed = []

    def fake_resumer(session):
        resumed.append((session.session_id, session.project_path, session.updated_at))

    server, base_url, config, config_path = _start_server(tmp_path, ccrider_db, fake_resumer)
    yield base_url, resumed, config, config_path
    server.shutdown()
    server.server_close()


@pytest.fixture
def e2e_server_failing_resume(tmp_path, ccrider_db):
    resumed = []

    def failing_resumer(session):
        raise RuntimeError("could not open Terminal")

    server, base_url, config, config_path = _start_server(tmp_path, ccrider_db, failing_resumer)
    yield base_url, resumed, config, config_path
    server.shutdown()
    server.server_close()


@pytest.fixture
def e2e_server_with_handoff(tmp_path, ccrider_db):
    """Server with a recording fake handoff. Yields (base_url, resumed, handoffs, hold).

    `hold` is a dict: set hold["release"] to a threading.Event to block the next handoff until
    the test sets it, or hold["error"] to a message to make the handoff fail. The fake `which`
    reports every agent binary as installed except `agy`.
    """
    resumed = []
    handoffs = []
    hold = {"release": None, "error": None}

    def fake_resumer(session):
        resumed.append(session.session_id)

    def fake_handoff(session, target):
        handoffs.append((session.session_id, target))
        if hold["release"] is not None:
            assert hold["release"].wait(timeout=10)
        if hold["error"]:
            raise RuntimeError(hold["error"])

    def fake_which(binary):
        return None if binary == "agy" else f"/fake/bin/{binary}"

    server, base_url, _, _ = _start_server(
        tmp_path, ccrider_db, fake_resumer, handoff=fake_handoff, which=fake_which,
    )
    yield base_url, resumed, handoffs, hold
    if hold["release"] is not None:
        hold["release"].set()
    server.shutdown()
    server.server_close()
