"""Local profiles for explicitly approved executable paths (never auto-run)."""
from dataclasses import dataclass, asdict
from pathlib import Path
import json
from .config import APP_DIR

PROFILE_PATH = APP_DIR / "profiles.json"

@dataclass(frozen=True)
class Profile:
    name: str
    executable: str


def validate_profile(name: str, executable: str) -> Profile:
    name = name.strip()
    if not name or len(name) > 64 or any(c in name for c in "\\/\n\r"):
        raise ValueError("Название профиля должно содержать 1–64 символа без слешей")
    path = Path(executable).expanduser().resolve(strict=True)
    if not path.is_file() or path.suffix.lower() != ".exe":
        raise ValueError("Профиль должен ссылаться на существующий .exe")
    return Profile(name, str(path))


def load_profiles(path: Path = PROFILE_PATH) -> list[Profile]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            return []
        return [Profile(x["name"], x["executable"]) for x in raw if isinstance(x, dict) and isinstance(x.get("name"), str) and isinstance(x.get("executable"), str)][:30]
    except (OSError, ValueError, TypeError, KeyError):
        return []


def save_profiles(profiles: list[Profile], path: Path = PROFILE_PATH) -> None:
    if len(profiles) > 30 or len({x.name.casefold() for x in profiles}) != len(profiles):
        raise ValueError("Максимум 30 профилей, названия должны быть уникальны")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps([asdict(x) for x in profiles], ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)
