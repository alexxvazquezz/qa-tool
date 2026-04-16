"""Config file management for the Holafly QA tool.

Stores user preferences at ~/.holafly-qa/config.toml. This lets the tool
remember the user's AVD name, port preferences, and other settings so
they only have to run `qa-tool init` once.
"""

import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

import tomli_w


CONFIG_DIR = Path.home() / ".holafly-qa"
CONFIG_FILE = CONFIG_DIR / "config.toml"


@dataclass
class Config:
    """User preferences stored between runs."""

    avd_name: str = ""
    mitm_port: int = 8080
    apk_dir: str = str(Path.home() / "Downloads")


def get_config_path() -> Path:
    """Return the full path to the config file."""
    return CONFIG_FILE


def load_config() -> Config:
    """Load config from disk. Returns default Config if file doesn't exist."""
    if not CONFIG_FILE.exists():
        return Config()

    with open(CONFIG_FILE, "rb") as f:
        data = tomllib.load(f)

    return Config(
        avd_name=data.get("avd_name", ""),
        mitm_port=data.get("mitm_port", 8080),
        apk_dir=data.get("apk_dir", str(Path.home() / "Downloads")),
    )


def save_config(config: Config) -> None:
    """Save config to disk, creating the config directory if needed."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    with open(CONFIG_FILE, "wb") as f:
        tomli_w.dump(asdict(config), f)