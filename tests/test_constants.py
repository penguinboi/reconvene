# ABOUTME: Tests for constants derived at import time rather than hardcoded.
# ABOUTME: Verifies VERSION is read from pyproject.toml, not duplicated by hand.
import tomllib
from pathlib import Path

from reconvene.constants import VERSION, BOT_PROMOTE_MESSAGE_COUNT, NOISE_MESSAGE_FLOOR


def test_version_matches_pyproject():
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    with pyproject.open("rb") as f:
        declared = tomllib.load(f)["project"]["version"]
    assert VERSION == declared


def test_heuristic_thresholds_are_the_validated_defaults():
    assert BOT_PROMOTE_MESSAGE_COUNT == 30
    assert NOISE_MESSAGE_FLOOR == 2
