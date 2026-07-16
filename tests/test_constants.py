# ABOUTME: Tests for constants derived at import time rather than hardcoded.
# ABOUTME: Verifies VERSION resolves from installed metadata (with a source-tree fallback).
import tomllib
from importlib.metadata import PackageNotFoundError
from pathlib import Path

import reconvene.constants as constants
from reconvene.constants import VERSION, BOT_PROMOTE_MESSAGE_COUNT, NOISE_MESSAGE_FLOOR


def test_version_matches_pyproject():
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    with pyproject.open("rb") as f:
        declared = tomllib.load(f)["project"]["version"]
    assert VERSION == declared


def test_read_version_uses_installed_metadata(monkeypatch):
    # When reconvene is installed, the version comes from package metadata -- crucially NOT from
    # an adjacent pyproject.toml, which does not exist in site-packages (reading it there crashed).
    monkeypatch.setattr(constants, "_pkg_version", lambda name: "9.9.9-from-metadata")
    assert constants._read_version() == "9.9.9-from-metadata"


def test_read_version_falls_back_to_pyproject_when_not_installed(monkeypatch):
    # Running from a source checkout that was never installed: fall back to the tree's pyproject.
    def not_installed(name):
        raise PackageNotFoundError(name)
    monkeypatch.setattr(constants, "_pkg_version", not_installed)
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    with pyproject.open("rb") as f:
        declared = tomllib.load(f)["project"]["version"]
    assert constants._read_version() == declared


def test_heuristic_thresholds_are_the_validated_defaults():
    assert BOT_PROMOTE_MESSAGE_COUNT == 30
    assert NOISE_MESSAGE_FLOOR == 2
