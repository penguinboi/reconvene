# ABOUTME: User-editable configuration — the generalization layer that replaces
# ABOUTME: pickup's hardcoded constants.py. Persisted to ~/.config/reconvene/config.json.
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .constants import CONFIG_PATH


@dataclass
class Config:
    code_root: str | None = None
    bot_names: set[str] = field(default_factory=set)
    hidden_names: set[str] = field(default_factory=set)
    recap_auth_mode: str = "claude_cli"
    api_key: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["bot_names"] = sorted(self.bot_names)
        d["hidden_names"] = sorted(self.hidden_names)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Config":
        return cls(
            code_root=d.get("code_root"),
            bot_names=set(d.get("bot_names", [])),
            hidden_names=set(d.get("hidden_names", [])),
            recap_auth_mode=d.get("recap_auth_mode", "claude_cli"),
            api_key=d.get("api_key"),
        )


def load_config(path=CONFIG_PATH) -> Config:
    path = Path(path)
    if not path.exists():
        return Config()
    with path.open() as f:
        return Config.from_dict(json.load(f))


def save_config(config: Config, path=CONFIG_PATH) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        json.dump(config.to_dict(), f, indent=2)
