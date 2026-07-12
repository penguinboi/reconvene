# ABOUTME: Classifies a session's project_path (drop/bot/real) and derives a canonical project name.
# ABOUTME: Folds git-worktree paths and case; bot/hidden lists and code_root come from the user's Config.
from .constants import (
    DROP_SUBSTRINGS, WORKTREE_MARKERS, OVERRIDE_MAP,
    BOT_PROMOTE_MESSAGE_COUNT, NOISE_MESSAGE_FLOOR,
)


def canonical_name(project_path: str) -> str:
    p = project_path.rstrip("/")
    for marker in WORKTREE_MARKERS:
        idx = p.find(marker)
        if idx != -1:
            p = p[:idx]
            break
    name = p.rsplit("/", 1)[-1].lower()
    return OVERRIDE_MAP.get(name, name)


def classify_category(project_path: str, config, message_count: int | None = None) -> str:
    for sub in DROP_SUBSTRINGS:
        if sub in project_path:
            return "drop"
    name = canonical_name(project_path)
    if name in config.hidden_names:
        return "drop"
    if name in config.bot_names:
        if message_count is not None and message_count > BOT_PROMOTE_MESSAGE_COUNT:
            return "real"
        return "bot"
    if config.code_root and not (
        project_path == config.code_root or project_path.startswith(config.code_root + "/")
    ):
        return "drop"
    if message_count is not None and message_count <= NOISE_MESSAGE_FLOOR:
        return "drop"
    return "real"
