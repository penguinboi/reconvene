# ABOUTME: Per-agent facts (name, binary, argv shapes, transcript location) for Claude, Codex and Antigravity.
# ABOUTME: Pure functions that build command lines; nothing here runs an agent.
import shlex
import shutil
from dataclasses import dataclass
from pathlib import Path

from .constants import MODEL

CODEX_UUID_LENGTH = 36


@dataclass(frozen=True)
class Agent:
    name: str
    label: str
    binary: str


AGENTS: dict[str, Agent] = {
    "claude": Agent("claude", "Claude", "claude"),
    "codex": Agent("codex", "Codex", "codex"),
    "antigravity": Agent("antigravity", "Antigravity", "agy"),
}


def get_agent(name: str) -> Agent:
    try:
        return AGENTS[name]
    except KeyError:
        raise ValueError(f"unknown agent {name!r}") from None


def is_supported(provider: str) -> bool:
    return provider in AGENTS


def agent_label(provider: str) -> str:
    """The display name for a session's provider, including agents reconvene cannot drive."""
    return AGENTS[provider].label if is_supported(provider) else provider.capitalize()


def require_resumable(provider: str) -> None:
    if not is_supported(provider):
        raise ValueError(
            f"reconvene can't resume {agent_label(provider)} sessions; hand it off to another agent instead"
        )


def extra_args_for(name: str, config) -> list[str]:
    """The user's configured extra flags for one agent, split shell-style."""
    get_agent(name)
    if config is None:
        return []
    return shlex.split(getattr(config, f"{name}_extra_args"))


def native_session_id(session) -> str:
    """The id the agent's own CLI accepts for resuming this session."""
    if session.resume_via:
        return session.resume_via
    if session.provider == "codex":
        return session.session_id[-CODEX_UUID_LENGTH:]
    return session.session_id


def resume_argv(session, prompt: str, extra: list[str]) -> list[str]:
    require_resumable(session.provider)
    binary = get_agent(session.provider).binary
    session_id = native_session_id(session)
    if session.provider == "claude":
        return [binary, "--resume", session_id, *extra, prompt]
    if session.provider == "codex":
        return [binary, "resume", *extra, session_id, prompt]
    return [binary, "--conversation", session_id, *extra]


def fresh_argv(name: str, prompt: str, extra: list[str]) -> list[str]:
    binary = get_agent(name).binary
    if name == "antigravity":
        return [binary, *extra, "-i", prompt]
    return [binary, *extra, prompt]


def headless_argv(name: str, prompt: str, output_file: str) -> list[str]:
    binary = get_agent(name).binary
    if name == "claude":
        return [binary, "-p", "--model", MODEL, "--no-session-persistence", "--tools=", prompt]
    if name == "codex":
        return [
            binary, "exec", "--ephemeral", "--skip-git-repo-check",
            "-s", "read-only", "-o", output_file, prompt,
        ]
    return [binary, "--mode", "plan", "--sandbox", "-p", prompt]


_TRANSCRIPT_GLOBS = {
    "claude": ".claude/projects/*/{id}.jsonl",
    "codex": ".codex/sessions/*/*/*/{id}.jsonl",
    "antigravity": ".gemini/antigravity-cli/conversations/{id}.db",
}


def transcript_path(session, home: Path) -> Path | None:
    if not is_supported(session.provider):
        return None
    pattern = _TRANSCRIPT_GLOBS[session.provider].format(id=session.session_id)
    return next(iter(sorted(Path(home).glob(pattern))), None)


def installed_agents(which=shutil.which) -> dict[str, bool]:
    return {name: which(agent.binary) is not None for name, agent in AGENTS.items()}
