"""Bounded, local diagnostic history. No network credentials are stored."""
from datetime import datetime, timezone
import json
from pathlib import Path
from .config import APP_DIR

HISTORY_PATH = APP_DIR / "history.json"
MAX_RECORDS = 100


def load_history(path: Path = HISTORY_PATH) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return []
        return [r for r in data if isinstance(r, dict) and isinstance(r.get("results"), dict)][-MAX_RECORDS:]
    except (OSError, ValueError, TypeError):
        return []


def record_scan(results: list[tuple[str, str]], path: Path = HISTORY_PATH) -> dict:
    record = {"timestamp": datetime.now(timezone.utc).isoformat(), "results": dict(results)}
    entries = load_history(path)
    entries.append(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(entries[-MAX_RECORDS:], ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)
    return record
