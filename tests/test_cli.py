# ABOUTME: Tests for the CLI entry point's port selection, argument handling, and
# ABOUTME: startup error paths (missing ccrider binary, no free port available).
import socket

import pytest

from reconvene import cli
from reconvene.cli import find_free_port


def test_find_free_port_returns_preferred_when_available():
    port = find_free_port(preferred=47001, tries=5)
    assert port == 47001


def test_find_free_port_skips_occupied_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 47002))
    sock.listen(1)
    try:
        port = find_free_port(preferred=47002, tries=5)
        assert port != 47002
    finally:
        sock.close()


def test_find_free_port_raises_when_none_available():
    sockets = []
    try:
        for offset in range(3):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(("127.0.0.1", 47010 + offset))
            sock.listen(1)
            sockets.append(sock)
        with pytest.raises(RuntimeError, match="no free port"):
            find_free_port(preferred=47010, tries=3)
    finally:
        for sock in sockets:
            sock.close()


def test_main_prints_clear_error_when_ccrider_missing(monkeypatch, capsys):
    def fake_run(cmd):
        raise FileNotFoundError("no such file: ccrider")
    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    rc = cli.main([], stdin_isatty=False)
    assert rc == 1
    assert "brew install neilberkman/tap/ccrider" in capsys.readouterr().err


def test_main_prints_clear_error_when_no_port_available(monkeypatch, capsys):
    monkeypatch.setattr(cli, "find_free_port", lambda: (_ for _ in ()).throw(RuntimeError("no free port found in range 4242-4251")))
    rc = cli.main(["--no-sync"], stdin_isatty=False)
    assert rc == 1
    assert "no free port found" in capsys.readouterr().err


def test_choose_frontend_web():
    assert cli._choose_frontend(input_fn=lambda prompt: "1") == "web"


def test_choose_frontend_tui():
    assert cli._choose_frontend(input_fn=lambda prompt: "2") == "tui"


def test_choose_frontend_reprompts_on_bad_input():
    answers = iter(["x", "", "2"])
    assert cli._choose_frontend(input_fn=lambda prompt: next(answers)) == "tui"


def test_choose_frontend_none_on_eof():
    def eof(prompt):
        raise EOFError
    assert cli._choose_frontend(input_fn=eof) is None


def test_main_non_tty_defaults_to_web(tmp_path):
    calls = []
    rc = cli.main(
        ["--no-sync", "--db", str(tmp_path / "x.db"), "--config", str(tmp_path / "c.json")],
        stdin_isatty=False,
        launch_web=lambda *a, **k: calls.append("web") or 0,
        launch_tui=lambda *a, **k: calls.append("tui") or 0,
    )
    assert rc == 0
    assert calls == ["web"]


def test_main_chooser_picks_tui(tmp_path):
    calls = []
    rc = cli.main(
        ["--no-sync", "--db", str(tmp_path / "x.db"), "--config", str(tmp_path / "c.json")],
        stdin_isatty=True, input_fn=lambda prompt: "2",
        launch_web=lambda *a, **k: calls.append("web") or 0,
        launch_tui=lambda *a, **k: calls.append("tui") or 0,
    )
    assert rc == 0
    assert calls == ["tui"]


def test_main_chooser_picks_web(tmp_path):
    calls = []
    rc = cli.main(
        ["--no-sync", "--db", str(tmp_path / "x.db"), "--config", str(tmp_path / "c.json")],
        stdin_isatty=True, input_fn=lambda prompt: "1",
        launch_web=lambda *a, **k: calls.append("web") or 0,
        launch_tui=lambda *a, **k: calls.append("tui") or 0,
    )
    assert calls == ["web"]


def test_main_chooser_eof_returns_0_without_launching(tmp_path):
    calls = []
    def eof(prompt):
        raise EOFError
    rc = cli.main(
        ["--no-sync", "--db", str(tmp_path / "x.db"), "--config", str(tmp_path / "c.json")],
        stdin_isatty=True, input_fn=eof,
        launch_web=lambda *a, **k: calls.append("web") or 0,
        launch_tui=lambda *a, **k: calls.append("tui") or 0,
    )
    assert rc == 0
    assert calls == []


def test_main_tui_passes_bots_flag(tmp_path):
    captured = {}
    cli.main(
        ["-b", "--no-sync", "--db", str(tmp_path / "x.db"), "--config", str(tmp_path / "c.json")],
        stdin_isatty=True, input_fn=lambda prompt: "2",
        launch_web=lambda *a, **k: 0,
        launch_tui=lambda config, db, cache, show_bots: captured.setdefault("show_bots", show_bots) or 0,
    )
    assert captured["show_bots"] is True
