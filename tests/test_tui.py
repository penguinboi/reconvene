# ABOUTME: Tests for the terminal frontend — rendering, entry ordering, and run_tui dispatch.
# ABOUTME: Injects a fake picker + fake resumer so no real fzf/claude ever runs.
from reconvene.config import Config
from reconvene.db import Session
from reconvene.journal import Project
from reconvene import tui
from tests.conftest import add_session, add_message


def _p(name, cat, sid, path, updated, count=1):
    return Project(name, cat, [Session(sid, path, updated, updated, 5, None, None) for _ in range(count)])


def test_render_line_format():
    p = _p("myproject", "real", "s1", "/Users/x/Code/myproject", "2026-07-08 10:00:00", count=2)
    line = tui.render_line(p)
    assert "myproject" in line and "2 sessions" in line and "·" in line


def test_render_preview_has_stats_and_recap():
    p = _p("myproject", "real", "s1", "/Users/x/Code/myproject", "2026-07-08 10:00:00")
    out = tui.render_preview(p, "did the sensor work")
    assert "myproject" in out
    assert "/Users/x/Code/myproject" in out or "~/Code/myproject" in out  # abbreviated path
    assert "did the sensor work" in out


def test_build_entries_orders_real_then_bots():
    real = [_p("realproj", "real", "r1", "/p/realproj", "2026-07-08 00:00:00")]
    bots = [_p("botproj", "bot", "b1", "/p/botproj", "2026-07-09 00:00:00")]
    entries = tui.build_entries(real, bots, show_bots=True)
    displays = [d for d, _ in entries]
    assert "realproj" in displays[0]
    assert any("automated" in d.lower() for d in displays)  # separator present
    assert entries[-1][1] == "b1"


def test_run_tui_resumes_selected(tmp_path, ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "wire up thresholds", sequence=1)
    resumed = []
    rc = tui.run_tui(
        Config(recap_auth_mode="none"), str(ccrider_db), str(tmp_path / "r.db"),
        picker=lambda lines: lines[0],  # pick the first entry ("s1\t...")
        resumer=lambda sid, cwd, updated_at, config: resumed.append((sid, cwd, updated_at)),
    )
    assert rc == 0
    assert resumed == [("s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00")]


def test_run_tui_no_pick_returns_0(tmp_path, ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "hi", sequence=1)
    resumed = []
    rc = tui.run_tui(
        Config(recap_auth_mode="none"), str(ccrider_db), str(tmp_path / "r.db"),
        picker=lambda lines: None,  # user pressed ESC
        resumer=lambda *a: resumed.append(a),
    )
    assert rc == 0
    assert resumed == []


def test_run_tui_separator_pick_does_not_resume(tmp_path, ccrider_db):
    add_session(ccrider_db, "b1", "/Users/x/Code/scoutbot", "2026-07-09 00:00:00", message_count=2)
    add_message(ccrider_db, "b1", "user", "score idea", sequence=1)
    add_session(ccrider_db, "r1", "/Users/x/Code/realproj", "2026-07-08 00:00:00", message_count=40)
    add_message(ccrider_db, "r1", "user", "real work", sequence=1)
    resumed = []
    rc = tui.run_tui(
        Config(recap_auth_mode="none", bot_names={"scoutbot"}), str(ccrider_db), str(tmp_path / "r.db"),
        show_bots=True,
        picker=lambda lines: next(l for l in lines if "automated" in l.lower()),  # the separator row
        resumer=lambda *a: resumed.append(a),
    )
    assert rc == 0
    assert resumed == []


def test_run_tui_empty_returns_1(tmp_path, ccrider_db):
    resumed = []
    rc = tui.run_tui(
        Config(recap_auth_mode="none"), str(ccrider_db), str(tmp_path / "r.db"),
        picker=lambda lines: lines[0] if lines else None,
        resumer=lambda *a: resumed.append(a),
    )
    assert rc == 1
    assert resumed == []


def test_run_tui_bots_hidden_without_flag(tmp_path, ccrider_db):
    # A real project keeps the view non-empty so the picker is genuinely invoked; the bot must
    # not appear in the lines without -b.
    add_session(ccrider_db, "r1", "/Users/x/Code/realproj", "2026-07-08 00:00:00", message_count=40)
    add_message(ccrider_db, "r1", "user", "real work", sequence=1)
    add_session(ccrider_db, "b1", "/Users/x/Code/scoutbot", "2026-07-09 00:00:00", message_count=2)
    add_message(ccrider_db, "b1", "user", "score idea", sequence=1)
    seen = {}
    tui.run_tui(
        Config(recap_auth_mode="none", bot_names={"scoutbot"}), str(ccrider_db), str(tmp_path / "r.db"),
        show_bots=False,
        picker=lambda lines: seen.setdefault("lines", lines) and None,
        resumer=lambda *a: None,
    )
    assert any("realproj" in l for l in seen["lines"])      # the real project is shown
    assert all("scoutbot" not in l for l in seen["lines"])  # bot section not shown without -b


def test_run_tui_only_bots_without_flag_returns_1(tmp_path, ccrider_db):
    # When every project is a bot and -b is off, there is nothing to show: return 1 with a hint,
    # rather than opening an empty picker.
    add_session(ccrider_db, "b1", "/Users/x/Code/scoutbot", "2026-07-09 00:00:00", message_count=2)
    add_message(ccrider_db, "b1", "user", "score idea", sequence=1)
    opened = []
    rc = tui.run_tui(
        Config(recap_auth_mode="none", bot_names={"scoutbot"}), str(ccrider_db), str(tmp_path / "r.db"),
        show_bots=False,
        picker=lambda lines: opened.append(lines),
        resumer=lambda *a: None,
    )
    assert rc == 1
    assert opened == []  # picker never opened on an empty view


def test_run_tui_missing_fzf_returns_1(tmp_path, ccrider_db, monkeypatch):
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "hi", sequence=1)
    monkeypatch.setattr("reconvene.tui.shutil.which", lambda name: None)
    rc = tui.run_tui(Config(recap_auth_mode="none"), str(ccrider_db), str(tmp_path / "r.db"))  # no picker -> real path
    assert rc == 1
