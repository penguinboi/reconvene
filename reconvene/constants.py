# ABOUTME: Paths and tunable constants for reconvene.
# ABOUTME: No personal project names live here — those go in the user's config.json.
import tomllib
from pathlib import Path


def _read_version() -> str:
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    with pyproject.open("rb") as f:
        return tomllib.load(f)["project"]["version"]


VERSION = _read_version()

HOME = Path.home()
CCRIDER_DB = HOME / ".config" / "ccrider" / "sessions.db"
RECAP_CACHE_DB = HOME / ".config" / "reconvene" / "recaps.db"
CONFIG_PATH = HOME / ".config" / "reconvene" / "config.json"

DROP_SUBSTRINGS = ("/private/", "/scratchpad")
WORKTREE_MARKERS = ("/.claude-worktrees/", "/.worktrees/", "--claude-worktrees")
OVERRIDE_MAP: dict[str, str] = {}

BOT_PROMOTE_MESSAGE_COUNT = 30
NOISE_MESSAGE_FLOOR = 2

RECENT_SESSIONS_FOR_RECAP = 3
RECAP_CONCURRENCY = 4
MODEL = "sonnet"
