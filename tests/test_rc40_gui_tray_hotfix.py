"""Regressions for mirrored UI resources and safe frameless minimization."""
from pathlib import Path
from types import SimpleNamespace

from vorqeli_connect.frameless import minimize


def test_source_and_embedded_gui_assets_match_byte_for_byte():
    root = Path(__file__).resolve().parents[1]
    for name in ('VORQELI-logo.png', 'VORQELI.ico', 'VORQELI-hosts-optional.txt'):
        source = root / 'assets' / name
        mirrored = root / 'src/vorqeli_connect/ui_assets' / name
        assert source.is_file() and mirrored.is_file()
        assert source.read_bytes() == mirrored.read_bytes(), name


def test_frameless_minimize_supports_legacy_non_tk_iconify():
    calls = []
    fake = SimpleNamespace(iconify=lambda: calls.append('iconify'))
    minimize(fake)
    assert calls == ['iconify']


def test_frameless_minimize_does_not_minimize_destroyed_tk_window():
    calls = []
    fake = SimpleNamespace(winfo_exists=lambda: False,
                           overrideredirect=lambda: True,
                           iconify=lambda: calls.append('iconify'))
    minimize(fake)
    assert calls == []
