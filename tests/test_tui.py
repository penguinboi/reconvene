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


def test_render_header_has_stats_no_body():
    p = _p("myproject", "real", "s1", "/Users/x/Code/myproject", "2026-07-08 10:00:00", count=2)
    out = tui.render_header(p)
    assert "myproject" in out
    assert "2 sessions" in out
    assert "/Users/x/Code/myproject" in out or "~/Code/myproject" in out  # abbreviated path


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
        Config(recap_auth_mode="none"), str(ccrider_db), str(tmp_path / "r.db"), str(tmp_path / "c.json"),
        picker=lambda lines: ("", lines[0]),  # pick the first entry ("s1\t...")
        resumer=lambda sid, cwd, updated_at, config: resumed.append((sid, cwd, updated_at)),
    )
    assert rc == 0
    assert resumed == [("s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00")]


def test_run_tui_no_pick_returns_0(tmp_path, ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "hi", sequence=1)
    resumed = []
    rc = tui.run_tui(
        Config(recap_auth_mode="none"), str(ccrider_db), str(tmp_path / "r.db"), str(tmp_path / "c.json"),
        picker=lambda lines: ("", None),  # user pressed ESC
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
        Config(recap_auth_mode="none", bot_names={"scoutbot"}), str(ccrider_db), str(tmp_path / "r.db"), str(tmp_path / "c.json"),
        show_bots=True,
        picker=lambda lines: ("", next(l for l in lines if "automated" in l.lower())),  # the separator row
        resumer=lambda *a: resumed.append(a),
    )
    assert rc == 0
    assert resumed == []


def test_run_tui_empty_returns_1(tmp_path, ccrider_db):
    resumed = []
    rc = tui.run_tui(
        Config(recap_auth_mode="none"), str(ccrider_db), str(tmp_path / "r.db"), str(tmp_path / "c.json"),
        picker=lambda lines: ("", lines[0]) if lines else ("", None),
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
        Config(recap_auth_mode="none", bot_names={"scoutbot"}), str(ccrider_db), str(tmp_path / "r.db"), str(tmp_path / "c.json"),
        show_bots=False,
        picker=lambda lines: seen.setdefault("lines", lines) and ("", None),
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
        Config(recap_auth_mode="none", bot_names={"scoutbot"}), str(ccrider_db), str(tmp_path / "r.db"), str(tmp_path / "c.json"),
        show_bots=False,
        picker=lambda lines: opened.append(lines) or ("", None),
        resumer=lambda *a: None,
    )
    assert rc == 1
    assert opened == []  # picker never opened on an empty view


def test_run_tui_missing_fzf_returns_1(tmp_path, ccrider_db, monkeypatch):
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "hi", sequence=1)
    monkeypatch.setattr("reconvene.tui.shutil.which", lambda name: None)
    rc = tui.run_tui(Config(recap_auth_mode="none"), str(ccrider_db), str(tmp_path / "r.db"), str(tmp_path / "c.json"))  # no picker -> real path
    assert rc == 1


def test_preview_command_references_the_preview_module_and_paths():
    import sys as _sys
    from pathlib import Path as _Path
    cmd = tui._preview_command("/db/sessions.db", "/cache/recaps.db", "/cfg/config.json")
    assert _sys.executable in cmd
    assert "-m reconvene._preview" in cmd
    assert "{1}" in cmd  # fzf substitutes the hidden session-id column
    assert "/db/sessions.db" in cmd and "/cache/recaps.db" in cmd and "/cfg/config.json" in cmd
    # PYTHONPATH points the subprocess at the package root so it imports under any install mode
    # (including a bare bin/reconvene symlink, whose runtime sys.path insert a child won't inherit).
    pkg_root = str(_Path(tui.__file__).resolve().parent.parent)
    assert f"PYTHONPATH={pkg_root}" in cmd or f"PYTHONPATH='{pkg_root}'" in cmd
    session_cmd = tui._preview_command("/db/x.db", "/c/r.db", "/cfg/c.json", session=True)
    assert session_cmd.endswith(" --session")


def test_run_tui_does_not_generate_recaps_up_front(tmp_path, ccrider_db, monkeypatch):
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "hi", sequence=1)
    # Config() defaults to recap_auth_mode="claude_cli"; if run_tui still generated recaps up front
    # it would call claude_runner. Record calls and assert it never happens.
    called = []
    monkeypatch.setattr("reconvene.recap.claude_runner",
                        lambda *a, **k: called.append(1) or "ONELINE: x\nDETAIL: x")
    seen = {}
    tui.run_tui(
        Config(), str(ccrider_db), str(tmp_path / "r.db"), str(tmp_path / "c.json"),
        picker=lambda lines: seen.setdefault("lines", lines) and ("", None),
        resumer=lambda *a: None,
    )
    assert seen["lines"]   # picker was reached with entry lines
    assert called == []    # no recap generation up front


def test_render_session_line_format(tmp_path, ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=7)
    add_message(ccrider_db, "s1", "user", "fix the flaky test", sequence=1)
    from reconvene.db import load_sessions
    (session,) = load_sessions(str(ccrider_db))
    line = tui.render_session_line(session, str(ccrider_db))
    sid, display = line.split("\t", 1)
    assert sid == "s1"
    assert "7 msgs" in display and "fix the flaky test" in display


def test_run_tui_ctrl_s_drills_into_sessions_and_resumes_picked(tmp_path, ccrider_db):
    add_session(ccrider_db, "old", "/Users/x/Code/myproject", "2026-07-01 00:00:00", message_count=50)
    add_message(ccrider_db, "old", "user", "the nas deep dive", sequence=1)
    add_session(ccrider_db, "new", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "new", "user", "quick tweak", sequence=1)
    resumed = []
    rc = tui.run_tui(
        Config(recap_auth_mode="none"), str(ccrider_db), str(tmp_path / "r.db"), str(tmp_path / "c.json"),
        picker=lambda lines: ("ctrl-s", lines[0]),          # drill into the (only) project
        session_picker=lambda lines: ("", next(l for l in lines if l.startswith("old\t"))),
        resumer=lambda sid, cwd, updated_at, config: resumed.append((sid, cwd)),
    )
    assert rc == 0
    assert resumed == [("old", "/Users/x/Code/myproject")]


def test_run_tui_ctrl_s_esc_returns_to_projects(tmp_path, ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "hi", sequence=1)
    resumed = []
    project_picks = iter([("ctrl-s", None), ("", None)])   # ctrl-s with no line, then quit
    rc = tui.run_tui(
        Config(recap_auth_mode="none"), str(ccrider_db), str(tmp_path / "r.db"), str(tmp_path / "c.json"),
        picker=lambda lines: next(project_picks),
        session_picker=lambda lines: ("", None),           # esc inside the session view
        resumer=lambda *a: resumed.append(a),
    )
    assert rc == 0
    assert resumed == []


def test_run_tui_session_view_esc_returns_to_projects(tmp_path, ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "hi", sequence=1)
    project_picks = iter([("ctrl-s", "s1\tmyproject · ..."), ("", None)])  # drill in, then quit
    project_pick_calls = []
    resumed = []

    def picker(lines):
        pick = next(project_picks)
        project_pick_calls.append(pick)
        return pick

    rc = tui.run_tui(
        Config(recap_auth_mode="none"), str(ccrider_db), str(tmp_path / "r.db"), str(tmp_path / "c.json"),
        picker=picker,
        session_picker=lambda lines: ("", None),   # esc from inside the session view
        resumer=lambda *a: resumed.append(a),
    )
    assert rc == 0
    assert resumed == []
    # the loop must re-show the project list after the session-view esc, not exit early
    assert len(project_pick_calls) == 2


def test_run_tui_ctrl_f_search_resumes_hit(tmp_path, ccrider_db):
    add_session(ccrider_db, "hit", "/Users/x/Code/homelab", "2026-07-07 00:00:00", message_count=30)
    add_message(ccrider_db, "hit", "user", "tune the synology nas", sequence=1)
    add_session(ccrider_db, "other", "/Users/x/Code/webapp", "2026-07-08 00:00:00", message_count=30)
    add_message(ccrider_db, "other", "user", "css fixes", sequence=1)
    resumed = []
    rc = tui.run_tui(
        Config(recap_auth_mode="none"), str(ccrider_db), str(tmp_path / "r.db"), str(tmp_path / "c.json"),
        picker=lambda lines: ("ctrl-f", None),
        search_picker=lambda query: "hit\thomelab · 12d ago · 1✓ · …",
        resumer=lambda sid, cwd, updated_at, config: resumed.append((sid, cwd)),
    )
    assert rc == 0
    assert resumed == [("hit", "/Users/x/Code/homelab")]


def test_run_tui_search_esc_returns_to_projects(tmp_path, ccrider_db):
    add_session(ccrider_db, "s1", "/Users/x/Code/myproject", "2026-07-08 00:00:00", message_count=12)
    add_message(ccrider_db, "s1", "user", "hi", sequence=1)
    picks = iter([("ctrl-f", None), ("", None)])
    resumed = []
    rc = tui.run_tui(
        Config(recap_auth_mode="none"), str(ccrider_db), str(tmp_path / "r.db"), str(tmp_path / "c.json"),
        picker=lambda lines: next(picks),
        search_picker=lambda query: None,   # esc in search view
        resumer=lambda *a: resumed.append(a),
    )
    assert rc == 0
    assert resumed == []


def test_run_tui_initial_search_skips_project_view(tmp_path, ccrider_db):
    add_session(ccrider_db, "hit", "/Users/x/Code/homelab", "2026-07-07 00:00:00", message_count=30)
    add_message(ccrider_db, "hit", "user", "pihole", sequence=1)
    resumed = []
    queries = []
    rc = tui.run_tui(
        Config(recap_auth_mode="none"), str(ccrider_db), str(tmp_path / "r.db"), str(tmp_path / "c.json"),
        picker=lambda lines: (_ for _ in ()).throw(AssertionError("project picker must not run")),
        search_picker=lambda query: queries.append(query) or "hit\thomelab · 12d ago · 1✓ · …",
        resumer=lambda sid, cwd, updated_at, config: resumed.append(sid),
        initial_search="pihole",
    )
    assert rc == 0
    assert queries == ["pihole"]
    assert resumed == ["hit"]


def test_search_reload_command_shape():
    cmd = tui._search_reload_command("/db/sessions.db")
    assert "-m reconvene._search" in cmd
    assert "{q}" in cmd
    assert "/db/sessions.db" in cmd
    assert "PYTHONPATH=" in cmd


def test_render_line_marks_topic_and_loose_kinds():
    p = _p("NAS & Pi-Hole", "real", "s1", "/Users/x/Code", "2026-07-08 10:00:00")
    p.kind = "topic"
    assert tui.render_line(p).endswith("· topic")
    p2 = _p("~/Code (loose sessions)", "real", "s2", "/Users/x/Code", "2026-07-08 10:00:00")
    p2.kind = "loose"
    assert tui.render_line(p2).endswith("· unorganized")
