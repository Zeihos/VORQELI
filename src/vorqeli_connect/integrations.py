"""Offline validation of manually supplied integration files.

This module never downloads binaries, runs external processes or changes Windows networking.
"""
from dataclasses import dataclass
from pathlib import Path
import hashlib

@dataclass(frozen=True)
class IntegrationFile:
    name: str
    filename: str
    sha256: str
    size: int

def inspect_file(path: str) -> IntegrationFile:
    file = Path(path).expanduser().resolve(strict=True)
    if not file.is_file():
        raise ValueError("Ожидается обычный файл")
    if file.suffix.lower() not in {".exe", ".py", ".bat", ".cmd"}:
        raise ValueError("Неподдерживаемое расширение файла")
    digest = hashlib.sha256()
    size = 0
    with file.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return IntegrationFile(file.name, str(file), digest.hexdigest(), size)

def verify_sha256(path: str, expected: str) -> bool:
    if len(expected) != 64 or any(c not in "0123456789abcdefABCDEF" for c in expected):
        raise ValueError("Некорректная контрольная сумма SHA-256")
    return inspect_file(path).sha256 == expected.lower()
