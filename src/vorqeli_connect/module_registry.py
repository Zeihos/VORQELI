"""Explicit adapters for future integrations; no downloads or privilege changes."""
from dataclasses import dataclass
from enum import Enum

class ModuleKind(str, Enum):
    DPI = "dpi"
    TELEGRAM = "telegram"

@dataclass(frozen=True)
class ModuleDescriptor:
    kind: ModuleKind
    display_name: str
    supported: bool
    detail: str

MODULES = (
    ModuleDescriptor(ModuleKind.DPI, "DPI", True, "Экспериментальный адаптер winws; нужен пакет Flowseal"),
    ModuleDescriptor(ModuleKind.TELEGRAM, "Telegram", True, "Консольный адаптер; нужны исходники tg-ws-proxy и Python"),
)

def get_module(kind: str) -> ModuleDescriptor:
    for module in MODULES:
        if module.kind.value == kind:
            return module
    raise ValueError(f"Неизвестный модуль: {kind}")
