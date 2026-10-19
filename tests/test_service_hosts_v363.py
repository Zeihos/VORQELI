"""v0.36.3: five service rows, GeoHide optional HOSTS snapshot, safety guards."""
from pathlib import Path
from unittest.mock import patch
from vorqeli_connect.diagnostics import SERVICES, check_all, check_group
from vorqeli_connect.hosts_overlay import parse_mappings, analyze_hosts, apply_optional_hosts, remove_optional_hosts


def test_five_service_rows():
    assert list(SERVICES) == ["Discord", "YouTube", "Telegram Web", "ChatGPT", "Microsoft (Copilot, Designer, Xbox)"]
    assert len(SERVICES["Microsoft (Copilot, Designer, Xbox)"]) == 3


def test_service_results_are_bounded_and_labelled():
    def fake(name, url, timeout=4.0):
        return name, 'Доступен' if 'copilot' in url else 'Нет ответа'
    with patch('vorqeli_connect.diagnostics.check_service', side_effect=fake):
        got = check_all()
    assert len(got) == 5
    assert 'Copilot: OK' in got[4][1]
    assert 'Designer: нет' in got[4][1]
    assert 'Xbox: нет' in got[4][1]


def test_host_snapshot_includes_tg_and_ai():
    root = Path(__file__).resolve().parents[1]
    first = parse_mappings((root / 'assets/VORQELI-hosts-optional.txt').read_text(encoding='utf8'))
    second = parse_mappings((root / 'src/vorqeli_connect/ui_assets/VORQELI-hosts-optional.txt').read_text(encoding='utf8'))
    assert first == second
    assert len(first) >= 1000
    for domain in ('web.telegram.org', 'chatgpt.com', 'claude.ai', 'copilot.microsoft.com',
                   'designer.microsoft.com', 'auth.xboxlive.com'):
        assert domain in first


def test_overlay_requires_explicit_action_and_preserves_unmanaged(tmp_path):
    root = Path(__file__).resolve().parents[1]
    mapping = (root / 'assets/VORQELI-hosts-optional.txt').read_text(encoding='utf8')
    host = tmp_path/'hosts'
    original = '127.0.0.1 localhost\n1.2.3.4 custom.example\n'
    host.write_text(original, encoding='utf8')
    inspect = analyze_hosts(host.read_text(), mapping)
    assert host.read_text() == original
    assert inspect['count'] > 1000
    apply_optional_hosts(host, mapping)
    assert 'chatgpt.com' in host.read_text()
    assert remove_optional_hosts(host)
    assert host.read_text() == original
