"""Append-only local event log with capped message length."""
from datetime import datetime, timezone
from pathlib import Path
import json
from .config import APP_DIR
LOG_PATH = APP_DIR / "events.jsonl"

def record_event(action: str, message: str, path: Path = LOG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    item = {"timestamp": datetime.now(timezone.utc).isoformat(), "action": str(action)[:64], "message": str(message)[:500]}
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(item, ensure_ascii=False) + "\n")

def recent_events(path: Path = LOG_PATH, limit: int = 30) -> list[dict]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-max(0, min(limit, 100)):]
        items = []
        for line in lines:
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    items.append(obj)
            except ValueError:
                continue
        return list(reversed(items))
    except OSError:
        return []
