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
    rc = cli.main([])
    assert rc == 1
    assert "brew install neilberkman/tap/ccrider" in capsys.readouterr().err


def test_main_prints_clear_error_when_no_port_available(monkeypatch, capsys):
    monkeypatch.setattr(cli, "find_free_port", lambda: (_ for _ in ()).throw(RuntimeError("no free port found in range 4242-4251")))
    rc = cli.main(["--no-sync"])
    assert rc == 1
    assert "no free port found" in capsys.readouterr().err
