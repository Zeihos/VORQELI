"""Human-facing status descriptions, separated from network-process states."""
from __future__ import annotations

HEADLINES = {
    'connected': 'Все модули запущены',
    'partial': 'Часть модулей не работает',
    'error': 'Подключение не удалось',
    'off': 'Готово к подключению',
}
MODULE_LABELS = {'on': 'ЗАПУЩЕН', 'error': 'ТРЕБУЕТ ВНИМАНИЯ', 'off': 'ОЖИДАЕТ'}


def main_status(state: str, busy: bool, disconnecting: bool = False) -> str:
    if busy:
        return 'Отключаем модули…' if disconnecting else 'Подключаем модули…'
    return HEADLINES.get(state, 'Проверяем соединение…')


def module_caption(state: str, enabled: bool) -> str:
    if not enabled:
        return 'ВЫКЛЮЧЕН В НАСТРОЙКАХ'
    return MODULE_LABELS.get(state, 'НЕИЗВЕСТНО')


def connection_disclaimer(state: str) -> str:
    if state == 'connected':
        return 'Все выбранные процессы запущены. Доступность сайтов проверяется отдельно.'
    if state == 'partial':
        return 'Некоторые компоненты недоступны. Подробности — в диагностике.'
    if state == 'error':
        return 'Проверьте журналы компонентов и настройки системы.'
    return 'DPI, Telegram и DNS управляются одной кнопкой.'
