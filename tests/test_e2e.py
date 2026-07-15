# ABOUTME: End-to-end test exercising the full stack: DB -> journal -> web API -> resume,
# ABOUTME: with a fake resumer (never actually opens a Terminal window in tests).
import json
import threading
import urllib.request

from reconvene.config import Config, save_config
from reconvene.web.server import serve
from tests.conftest import add_session, add_message


def test_full_journal_and_resume_flow(tmp_path, ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-01 00:00:00", message_count=40)
    add_message(ccrider_db, "s1", "user", "build the thing", sequence=1)
    add_session(ccrider_db, "s2", "/Users/x/Code/scoutbot", "2026-07-02 00:00:00", message_count=2)
    add_message(ccrider_db, "s2", "user", "score this idea", sequence=1)

    config_path = tmp_path / "config.json"
    config = Config(bot_names={"scoutbot"})
    save_config(config, config_path)

    resumed = []
    fake_recap_runner = lambda prompt: "ONELINE: test recap\nDETAIL: test"
    server = serve(config, str(ccrider_db), str(tmp_path / "recaps.db"), str(config_path),
                    lambda sid, cwd, updated_at: resumed.append((sid, cwd, updated_at)),
                    recap_runner=fake_recap_runner, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"

        with urllib.request.urlopen(f"{base_url}/api/journal") as resp:
            journal = json.loads(resp.read())
        assert [p["name"] for p in journal["real"]] == ["myproject"]
        assert [p["name"] for p in journal["bots"]] == ["scoutbot"]

        req = urllib.request.Request(f"{base_url}/api/resume/s1", method="POST", data=b"")
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
        assert result["status"] == "resumed"
        assert resumed == [("s1", "/Users/x/Code/myproject", "2026-07-01 00:00:00")]
    finally:
        server.shutdown()
        server.server_close()
