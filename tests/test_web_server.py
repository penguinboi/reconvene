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
    def fake_resumer(session_id, cwd, updated_at):
        resumed.append((session_id, cwd, updated_at))
    fake_recap_runner = lambda prompt: "ONELINE: test recap\nDETAIL: test"
    server = serve(config, str(ccrider_db), str(tmp_path / "recaps.db"), str(tmp_path / "config.json"),
                   fake_resumer, recap_runner=fake_recap_runner, port=0)
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


def test_resume_calls_resumer_with_session_and_path(running_server):
    base_url, resumed, _ = running_server
    req = urllib.request.Request(f"{base_url}/api/resume/r1", method="POST", data=b"")
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    assert data["status"] == "resumed"
    assert resumed == [("r1", "/Users/x/Code/myproject", "2026-07-08 00:00:00")]


def test_resume_unknown_session_is_404(running_server):
    base_url, resumed, _ = running_server
    req = urllib.request.Request(f"{base_url}/api/resume/does-not-exist", method="POST", data=b"")
    with pytest.raises(HTTPError) as exc:
        urllib.request.urlopen(req)
    assert exc.value.code == 404
    assert resumed == []


def test_resume_resumer_failure_returns_500(tmp_path, ccrider_db):
    add_session(ccrider_db, "r1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "r1", "user", "wire up thresholds", sequence=1)
    config = Config()
    def failing_resumer(session_id, cwd, updated_at):
        raise RuntimeError("osascript not found")
    fake_recap_runner = lambda prompt: "ONELINE: test recap\nDETAIL: test"
    server = serve(config, str(ccrider_db), str(tmp_path / "recaps.db"), str(tmp_path / "config.json"),
                   failing_resumer, recap_runner=fake_recap_runner, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        req = urllib.request.Request(f"{base_url}/api/resume/r1", method="POST", data=b"")
        with pytest.raises(HTTPError) as exc:
            urllib.request.urlopen(req)
        assert exc.value.code == 500
    finally:
        server.shutdown()
        server.server_close()


def test_recap_endpoint_returns_derived_recap_without_llm(running_server):
    # running_server's Config() defaults to recap_auth_mode="claude_cli", but no real
    # `claude` binary is invoked here — the server is wired up with a fake recap_runner,
    # so the response is the deterministic text that fake returns.
    base_url, _, _ = running_server
    with urllib.request.urlopen(f"{base_url}/api/recap/myproject") as resp:
        data = json.loads(resp.read())
    assert data["oneline"] == "test recap"
    assert data["full"] == "test"
    assert data["excerpt"] == "test"


def test_recap_endpoint_excerpt_is_truncated_to_three_sentences(tmp_path, ccrider_db):
    add_session(ccrider_db, "r1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "r1", "user", "wire up thresholds", sequence=1)
    config = Config()
    fake_recap_runner = lambda prompt: (
        "ONELINE: test recap\n"
        "DETAIL: Sentence one. Sentence two. Sentence three. Sentence four. Sentence five."
    )
    server = serve(config, str(ccrider_db), str(tmp_path / "recaps.db"), str(tmp_path / "config.json"),
                   lambda s, c, u: None, recap_runner=fake_recap_runner, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        with urllib.request.urlopen(f"{base_url}/api/recap/myproject") as resp:
            data = json.loads(resp.read())
        assert data["excerpt"] == "Sentence one. Sentence two. Sentence three."
    finally:
        server.shutdown()
        server.server_close()


def test_recap_endpoint_unknown_project_is_404(running_server):
    base_url, _, _ = running_server
    with pytest.raises(HTTPError) as exc:
        urllib.request.urlopen(f"{base_url}/api/recap/does-not-exist")
    assert exc.value.code == 404


def test_recap_endpoint_url_decodes_the_project_name(tmp_path, ccrider_db):
    # A project whose directory name has a space (or #, ?, non-ASCII) arrives percent-encoded.
    # Without decoding, "my%20app" never matches the project "my app" and the recap 404s forever.
    add_session(ccrider_db, "r1", "/Users/x/Code/my app", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "r1", "user", "hi", sequence=1)
    config = Config()
    fake_recap_runner = lambda prompt: "ONELINE: spaced name recap\nDETAIL: detail"
    server = serve(config, str(ccrider_db), str(tmp_path / "recaps.db"), str(tmp_path / "config.json"),
                   lambda s, c, u: None, recap_runner=fake_recap_runner, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        with urllib.request.urlopen(f"{base_url}/api/recap/my%20app") as resp:
            data = json.loads(resp.read())
        assert data["oneline"] == "spaced name recap"
    finally:
        server.shutdown()
        server.server_close()


def test_settings_get_lists_projects_and_config(running_server):
    base_url, _, _ = running_server
    with urllib.request.urlopen(f"{base_url}/api/settings") as resp:
        data = json.loads(resp.read())
    assert any(p["name"] == "myproject" for p in data["projects"])
    assert data["config"]["recap_auth_mode"] == "claude_cli"
    assert data["config"]["hidden_path_substrings"] == []


def test_settings_get_includes_hidden_projects_so_they_can_be_unhidden(tmp_path, ccrider_db):
    # A project the user hid must still appear in the settings table (as a "Hidden"/"drop" row),
    # otherwise there is no UI to un-hide it -- and a later save would silently drop it from
    # hidden_names entirely. It must NOT appear on the journal, though.
    add_session(ccrider_db, "r1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "r1", "user", "visible", sequence=1)
    add_session(ccrider_db, "h1", "/Users/x/Code/secretproj", "2026-07-09 00:00:00", message_count=12)
    add_message(ccrider_db, "h1", "user", "hidden work", sequence=1)
    config = Config(hidden_names={"secretproj"})
    fake_recap_runner = lambda prompt: "ONELINE: t\nDETAIL: t"
    server = serve(config, str(ccrider_db), str(tmp_path / "recaps.db"), str(tmp_path / "config.json"),
                   lambda s, c, u: None, recap_runner=fake_recap_runner, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        with urllib.request.urlopen(f"{base_url}/api/settings") as resp:
            settings = json.loads(resp.read())
        with urllib.request.urlopen(f"{base_url}/api/journal") as resp:
            journal = json.loads(resp.read())
        settings_names = {p["name"] for p in settings["projects"]}
        assert "secretproj" in settings_names   # shown in settings, so it can be un-hidden
        hidden = next(p for p in settings["projects"] if p["name"] == "secretproj")
        assert hidden["category"] == "drop"     # surfaced with the "Hidden" option's value
        journal_names = {p["name"] for p in journal["real"] + journal["bots"]}
        assert "secretproj" not in journal_names  # still hidden from the journal
    finally:
        server.shutdown()
        server.server_close()


def test_settings_get_never_returns_the_api_key(tmp_path, ccrider_db):
    # The secret must never be echoed to the browser -- only whether one is set. This removes
    # the value from any response an attacker could read (e.g. via a DNS-rebinding fetch).
    add_session(ccrider_db, "r1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "r1", "user", "wire up thresholds", sequence=1)
    config = Config(recap_auth_mode="api_key", api_key="sk-secret-should-not-leak")
    fake_recap_runner = lambda prompt: "ONELINE: test recap\nDETAIL: test"
    server = serve(config, str(ccrider_db), str(tmp_path / "recaps.db"), str(tmp_path / "config.json"),
                   lambda s, c, u: None, recap_runner=fake_recap_runner, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        with urllib.request.urlopen(f"{base_url}/api/settings") as resp:
            raw = resp.read()
        assert b"sk-secret-should-not-leak" not in raw
        data = json.loads(raw)
        assert data["config"]["api_key"] is None
        assert data["config"]["api_key_set"] is True
    finally:
        server.shutdown()
        server.server_close()


def test_settings_post_keeps_existing_api_key_when_field_blank(tmp_path, ccrider_db):
    # Because the GET no longer returns the key, a save with a blank api_key field must NOT
    # wipe the stored key -- blank means "leave it as-is".
    add_session(ccrider_db, "r1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "r1", "user", "wire up thresholds", sequence=1)
    config = Config(recap_auth_mode="api_key", api_key="sk-already-saved")
    config_path = str(tmp_path / "config.json")
    fake_recap_runner = lambda prompt: "ONELINE: test recap\nDETAIL: test"
    server = serve(config, str(ccrider_db), str(tmp_path / "recaps.db"), config_path, lambda s, c, u: None,
                   recap_runner=fake_recap_runner, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        payload = json.dumps({
            "bot_names": [], "hidden_names": [],
            "recap_auth_mode": "api_key", "api_key": None,
        }).encode()
        req = urllib.request.Request(f"{base_url}/api/settings", method="POST", data=payload,
                                      headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req):
            pass
        assert config.api_key == "sk-already-saved"  # unchanged, not wiped
    finally:
        server.shutdown()
        server.server_close()


def test_settings_post_saves_overrides(tmp_path, ccrider_db):
    add_session(ccrider_db, "r1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "r1", "user", "wire up thresholds", sequence=1)
    config = Config()
    config_path = str(tmp_path / "config.json")
    fake_recap_runner = lambda prompt: "ONELINE: test recap\nDETAIL: test"
    server = serve(config, str(ccrider_db), str(tmp_path / "recaps.db"), config_path, lambda s, c, u: None,
                   recap_runner=fake_recap_runner, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        payload = json.dumps({
            "bot_names": ["myproject"],
            "hidden_names": [],
            "recap_auth_mode": "none",
            "api_key": None,
        }).encode()
        req = urllib.request.Request(f"{base_url}/api/settings", method="POST", data=payload,
                                      headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
        assert data["status"] == "saved"
        assert config.bot_names == {"myproject"}
        assert config.recap_auth_mode == "none"
    finally:
        server.shutdown()
        server.server_close()


def test_settings_post_persists_to_configured_path_not_real_config(tmp_path, ccrider_db):
    add_session(ccrider_db, "r1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "r1", "user", "wire up thresholds", sequence=1)
    config = Config()
    config_path = tmp_path / "config.json"
    fake_recap_runner = lambda prompt: "ONELINE: test recap\nDETAIL: test"
    server = serve(config, str(ccrider_db), str(tmp_path / "recaps.db"), str(config_path), lambda s, c, u: None,
                   recap_runner=fake_recap_runner, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        payload = json.dumps({
            "bot_names": ["myproject"],
            "hidden_names": [],
            "recap_auth_mode": "none",
            "api_key": None,
        }).encode()
        req = urllib.request.Request(f"{base_url}/api/settings", method="POST", data=payload,
                                      headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req):
            pass
        assert config_path.exists()
        on_disk = json.loads(config_path.read_text())
        assert on_disk["bot_names"] == ["myproject"]
        assert on_disk["recap_auth_mode"] == "none"
    finally:
        server.shutdown()
        server.server_close()


def test_settings_post_saves_terminal_app_and_extra_args(tmp_path, ccrider_db):
    add_session(ccrider_db, "r1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "r1", "user", "wire up thresholds", sequence=1)
    config = Config()
    config_path = tmp_path / "config.json"
    fake_recap_runner = lambda prompt: "ONELINE: test recap\nDETAIL: test"
    server = serve(config, str(ccrider_db), str(tmp_path / "recaps.db"), str(config_path), lambda s, c, u: None,
                   recap_runner=fake_recap_runner, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        payload = json.dumps({
            "bot_names": [],
            "hidden_names": [],
            "recap_auth_mode": "none",
            "api_key": None,
            "terminal_app": "iTerm2",
            "claude_extra_args": "--dangerously-skip-permissions",
        }).encode()
        req = urllib.request.Request(f"{base_url}/api/settings", method="POST", data=payload,
                                      headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req):
            pass
        assert config.terminal_app == "iTerm2"
        assert config.claude_extra_args == "--dangerously-skip-permissions"
        on_disk = json.loads(config_path.read_text())
        assert on_disk["terminal_app"] == "iTerm2"
        assert on_disk["claude_extra_args"] == "--dangerously-skip-permissions"
    finally:
        server.shutdown()
        server.server_close()


def test_settings_post_saves_hidden_path_substrings(tmp_path, ccrider_db):
    add_session(ccrider_db, "r1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "r1", "user", "wire up thresholds", sequence=1)
    config = Config()
    config_path = tmp_path / "config.json"
    fake_recap_runner = lambda prompt: "ONELINE: test recap\nDETAIL: test"
    server = serve(config, str(ccrider_db), str(tmp_path / "recaps.db"), str(config_path), lambda s, c, u: None,
                   recap_runner=fake_recap_runner, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        payload = json.dumps({
            "bot_names": [],
            "hidden_names": [],
            "hidden_path_substrings": ["sarb_agent_", "scratch-"],
            "recap_auth_mode": "none",
            "api_key": None,
        }).encode()
        req = urllib.request.Request(f"{base_url}/api/settings", method="POST", data=payload,
                                      headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req):
            pass
        assert config.hidden_path_substrings == {"sarb_agent_", "scratch-"}
        on_disk = json.loads(config_path.read_text())
        assert sorted(on_disk["hidden_path_substrings"]) == ["sarb_agent_", "scratch-"]
    finally:
        server.shutdown()
        server.server_close()


def test_api_journal_includes_recency_bucket(tmp_path, ccrider_db):
    add_session(ccrider_db, "r1", "/Users/x/Code/myproject", "2020-01-01 00:00:00", message_count=12)
    add_message(ccrider_db, "r1", "user", "wire up thresholds", sequence=1)
    config = Config()
    fake_recap_runner = lambda prompt: "ONELINE: test recap\nDETAIL: test"
    server = serve(config, str(ccrider_db), str(tmp_path / "recaps.db"), str(tmp_path / "config.json"),
                   lambda s, c, u: None, recap_runner=fake_recap_runner, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        with urllib.request.urlopen(f"{base_url}/api/journal") as resp:
            data = json.loads(resp.read())
        assert data["real"][0]["recency"] == "stale"
    finally:
        server.shutdown()
        server.server_close()


def test_api_journal_includes_last_active_relative_and_cwd(tmp_path, ccrider_db):
    add_session(ccrider_db, "r1", "/tmp/some/fake/project", "2020-01-01 00:00:00", message_count=12)
    add_message(ccrider_db, "r1", "user", "wire up thresholds", sequence=1)
    config = Config()
    fake_recap_runner = lambda prompt: "ONELINE: test recap\nDETAIL: test"
    server = serve(config, str(ccrider_db), str(tmp_path / "recaps.db"), str(tmp_path / "config.json"),
                   lambda s, c, u: None, recap_runner=fake_recap_runner, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        with urllib.request.urlopen(f"{base_url}/api/journal") as resp:
            data = json.loads(resp.read())
        assert data["real"][0]["last_active_relative"].endswith("y ago")
        assert data["real"][0]["cwd"] == "/tmp/some/fake/project"
    finally:
        server.shutdown()
        server.server_close()


def test_post_with_foreign_origin_is_forbidden(running_server):
    # Classic CSRF: a cross-origin POST carries the attacker's Origin. It must be rejected
    # before the config is touched.
    base_url, _, config = running_server
    before = set(config.bot_names)
    payload = json.dumps({
        "bot_names": ["myproject"], "hidden_names": [],
        "recap_auth_mode": "none", "api_key": None,
    }).encode()
    req = urllib.request.Request(
        f"{base_url}/api/settings", method="POST", data=payload,
        headers={"Content-Type": "application/json", "Origin": "https://evil.example"},
    )
    with pytest.raises(HTTPError) as exc:
        urllib.request.urlopen(req)
    assert exc.value.code == 403
    assert config.bot_names == before  # config was not poisoned


def test_get_with_foreign_host_is_forbidden(running_server):
    # DNS rebinding: the rebound request still carries the attacker's hostname in Host.
    base_url, _, _ = running_server
    req = urllib.request.Request(f"{base_url}/api/journal", headers={"Host": "evil.example"})
    with pytest.raises(HTTPError) as exc:
        urllib.request.urlopen(req)
    assert exc.value.code == 403


def test_post_with_foreign_host_is_forbidden(running_server):
    # The Host allowlist guards writes too, not just reads.
    base_url, _, config = running_server
    before = set(config.bot_names)
    payload = json.dumps({
        "bot_names": ["myproject"], "hidden_names": [],
        "recap_auth_mode": "none", "api_key": None,
    }).encode()
    req = urllib.request.Request(
        f"{base_url}/api/settings", method="POST", data=payload,
        headers={"Content-Type": "application/json", "Host": "evil.example"},
    )
    with pytest.raises(HTTPError) as exc:
        urllib.request.urlopen(req)
    assert exc.value.code == 403
    assert config.bot_names == before


def test_post_with_matching_origin_succeeds(running_server):
    # The real UI flow: a same-origin POST carrying the correct Host and a matching Origin.
    base_url, _, config = running_server
    port = base_url.rsplit(":", 1)[1]
    payload = json.dumps({
        "bot_names": ["myproject"], "hidden_names": [],
        "recap_auth_mode": "none", "api_key": None,
    }).encode()
    req = urllib.request.Request(
        f"{base_url}/api/settings", method="POST", data=payload,
        headers={"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{port}"},
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
    assert config.bot_names == {"myproject"}


def test_post_without_origin_succeeds(running_server):
    # Non-browser clients omit Origin; the Host allowlist still applies, but absence of Origin
    # is deliberately allowed (documented choice).
    base_url, _, _ = running_server
    payload = json.dumps({
        "bot_names": [], "hidden_names": [],
        "recap_auth_mode": "none", "api_key": None,
    }).encode()
    req = urllib.request.Request(
        f"{base_url}/api/settings", method="POST", data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200


def test_static_path_with_foreign_host_is_forbidden(running_server):
    # Exercises the bare-403 branch of _forbidden (a non-/api path), not just the JSON branch.
    base_url, _, _ = running_server
    req = urllib.request.Request(f"{base_url}/", headers={"Host": "evil.example"})
    with pytest.raises(HTTPError) as exc:
        urllib.request.urlopen(req)
    assert exc.value.code == 403


def test_api_search_returns_session_hits(running_server, ccrider_db):
    base_url, _, _ = running_server
    add_session(ccrider_db, "s9", "/Users/x/Code/netstuff", "2026-07-09 00:00:00", message_count=8)
    add_message(ccrider_db, "s9", "user", "set up pihole dns blocking", sequence=1)
    with urllib.request.urlopen(f"{base_url}/api/search?q=pihole") as resp:
        data = json.loads(resp.read())
    (hit,) = data["results"]
    assert hit["session_id"] == "s9"
    assert hit["project"] == "netstuff"
    assert hit["hits"] == 1
    assert "«pihole»" in hit["snippet"]
    assert hit["cwd"] == "/Users/x/Code/netstuff"  # not under the test runner's real $HOME


def test_api_search_empty_query_returns_empty(running_server):
    base_url, _, _ = running_server
    with urllib.request.urlopen(f"{base_url}/api/search?q=") as resp:
        assert json.loads(resp.read()) == {"results": []}


def test_api_resume_works_for_unclassified_sessions(running_server, ccrider_db):
    # A 2-message session is noise-dropped from the journal, but search can surface it,
    # so resume must find it too.
    base_url, resumed, _ = running_server
    add_session(ccrider_db, "tiny", "/Users/x/Code/scratchpaddy", "2026-07-09 00:00:00", message_count=2)
    add_message(ccrider_db, "tiny", "user", "quick thing", sequence=1)
    req = urllib.request.Request(f"{base_url}/api/resume/tiny", method="POST")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
    assert resumed == [("tiny", "/Users/x/Code/scratchpaddy", "2026-07-09 00:00:00")]


def test_api_sessions_lists_project_sessions_newest_first(running_server, ccrider_db):
    base_url, _, _ = running_server
    add_session(ccrider_db, "r2", "/Users/x/Code/myproject", "2026-07-09 00:00:00", message_count=20)
    add_message(ccrider_db, "r2", "user", "second thread", sequence=1)
    with urllib.request.urlopen(f"{base_url}/api/sessions/myproject") as resp:
        data = json.loads(resp.read())
    assert [s["session_id"] for s in data["sessions"]] == ["r2", "r1"]
    assert data["sessions"][0]["first_msg"] == "second thread"
    assert data["sessions"][0]["message_count"] == 20


def test_api_sessions_unknown_project_404(running_server):
    base_url, _, _ = running_server
    with pytest.raises(HTTPError) as exc:
        urllib.request.urlopen(f"{base_url}/api/sessions/nope")
    assert exc.value.code == 404


def test_post_with_localhost_host_and_origin_succeeds(running_server):
    # The allowlist accepts localhost as well as 127.0.0.1; confirm that branch end-to-end.
    base_url, _, config = running_server
    port = base_url.rsplit(":", 1)[1]
    payload = json.dumps({
        "bot_names": ["myproject"], "hidden_names": [],
        "recap_auth_mode": "none", "api_key": None,
    }).encode()
    req = urllib.request.Request(
        f"{base_url}/api/settings", method="POST", data=payload,
        headers={"Content-Type": "application/json",
                 "Host": f"localhost:{port}", "Origin": f"http://localhost:{port}"},
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
    assert config.bot_names == {"myproject"}


def test_api_journal_reports_kind_and_topic_groups(running_server, ccrider_db, tmp_path):
    base_url, _, _ = running_server
    for i, sub in enumerate(("alpha", "beta", "gamma")):
        add_session(ccrider_db, f"p{i}", f"/Users/x/Code/{sub}", "2026-07-01 00:00:00", message_count=10)
        add_message(ccrider_db, f"p{i}", "user", "work", sequence=1)
    add_session(ccrider_db, "l1", "/Users/x/Code", "2026-07-09 00:00:00", message_count=20)
    add_message(ccrider_db, "l1", "user", "loose thread", sequence=1)
    with urllib.request.urlopen(f"{base_url}/api/journal") as resp:
        data = json.loads(resp.read())
    kinds = {p["name"]: p["kind"] for p in data["real"]}
    assert kinds["myproject"] == "project"
    assert any(k == "loose" for k in kinds.values())
