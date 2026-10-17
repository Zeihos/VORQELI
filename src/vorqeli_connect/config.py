"""Persist user preferences in their profile, not beside an executable."""
from dataclasses import asdict, dataclass
from pathlib import Path
import json
import os

APP_DIR = Path(os.environ.get("APPDATA", str(Path.home()))) / "VorqeliConnect"
CONFIG_PATH = APP_DIR / "settings.json"


@dataclass
class Settings:
    dpi_profile: str = "Not configured"
    telegram_port: int = 1080
    launch_at_startup: bool = False


def load_settings(path: Path = CONFIG_PATH) -> Settings:
    if not path.exists():
        return Settings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        selected = {k: v for k, v in data.items() if k in Settings.__dataclass_fields__}
        return Settings(**selected)
    except (OSError, ValueError, TypeError):
        return Settings()


def save_settings(settings: Settings, path: Path = CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
