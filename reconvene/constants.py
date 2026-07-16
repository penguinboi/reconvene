# ABOUTME: Paths and tunable constants for reconvene.
# ABOUTME: No personal project names live here — those go in the user's config.json.
from importlib.metadata import PackageNotFoundError, version as _pkg_version
from pathlib import Path


def _read_version() -> str:
    # Prefer installed package metadata. Reading an adjacent pyproject.toml (the old approach)
    # crashes for any pip/pipx install, since site-packages has no pyproject.toml. Fall back to
    # the source tree's pyproject only when running uninstalled from a checkout.
    try:
        return _pkg_version("reconvene")
    except PackageNotFoundError:
        import tomllib
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
