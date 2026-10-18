"""Bounded viewer for subprocess logs with local secret redaction."""
from __future__ import annotations
import re
from pathlib import Path


def tail_log(path: str | Path, max_bytes: int = 65536) -> str:
    if not isinstance(max_bytes, int) or not 1 <= max_bytes <= 1024 * 1024:
        raise ValueError("Недопустимый размер просмотра журнала")
    file = Path(path)
    if not file.is_file():
        return "Журнал ещё не создан."
    with file.open("rb") as stream:
        stream.seek(0, 2)
        size = stream.tell()
        position = max(0, size - max_bytes)
        stream.seek(position)
        data = stream.read(max_bytes)
    header = "[Показана последняя часть журнала]\n" if position else ""
    return header + data.decode("utf-8", errors="replace")


def redact_secrets(text: str, *secrets: str) -> str:
    for secret in secrets:
        if isinstance(secret, str) and len(secret) >= 8:
            text = re.sub(re.escape(secret), "[СКРЫТО]", text, flags=re.IGNORECASE)
    # Handle common CLI and diagnostic output even when the known secret is unavailable.
    # Some programs log --secret=HEX or "Generated secret: HEX".
    text = re.sub(
        r"(?i)((?:--secret|(?:generated\s+)?secret)\s*(?:=|:)\s*|--secret\s+)[0-9a-f]{32}\b",
        r"\1[СКРЫТО]", text,
    )
    return text


def failure_hint(log: str, exit_code: int | None) -> str:
    lower = log.lower()
    if "modulenotfounderror" in lower or "no module named" in lower:
        return "Не хватает Python-зависимостей. Установите зависимости tg-ws-proxy из его папки: py -m pip install -e ."
    if "permission denied" in lower or "access is denied" in lower or "error 5" in lower:
        return "Возможно, не хватает прав доступа. Проверьте права Windows и документацию движка."
    if "address already in use" in lower or "winerror 10048" in lower:
        return "Указанный порт уже занят. Выберите другой порт и повторите запуск."
    if "windivert" in lower and any(word in lower for word in ("fail", "error", "access")):
        return "Ошибка WinDivert. Проверьте установленный пакет и права Windows."
    if exit_code is None:
        return "Нет информации о завершении процесса."
    return f"Процесс завершился с кодом {exit_code}. Проверьте журнал для подробностей."
