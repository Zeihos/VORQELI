"""Offline acceptance checks for GeoHide + Flowseal HOSTS-only mode.

Every file write is to pytest's temporary directory, never the real HOSTS.
"""
from pathlib import Path
import pytest

from vorqeli_connect import hosts_connection as hosts
from vorqeli_connect import unified
from vorqeli_connect.config import Settings


def geo_sample():
    rows = ''.join(f'8.8.8.8 sample{i}.example.com\n' for i in range(205))
    return ('### geohide.ru: hosts file\n'
            '# Последнее обновление: 22.11.2026 12:00:00\n'
            '# Регион серверов: RU\n'
            + rows +
            '### geohide.ru: end hosts file\n')


def flow_sample():
    names = ['github.com', 'discord.com'] + [f'flow{i}.example.org' for i in range(15)]
    return ''.join(f'1.1.1.1 {name}\n' for name in names)


def test_flowseal_parser_rejects_unsafe_ip_and_missing_domains():
    with pytest.raises(ValueError):
        hosts.parse_flowseal_hosts(flow_sample().replace('1.1.1.1', '127.0.0.1'))
    with pytest.raises(ValueError):
        hosts.parse_flowseal_hosts('1.1.1.1 discord.com\n')


def test_combined_hosts_apply_restore_preserves_manual_lines(tmp_path):
    system_hosts = tmp_path / 'hosts'
    journal = tmp_path / 'journal.json'
    original = '127.0.0.1 localhost\n9.9.9.9 user.example.org\n'
    system_hosts.write_text(original, encoding='utf-8')
    applied = hosts.enable_hosts_only(
        path=system_hosts, journal_path=journal,
        geo_fetch=geo_sample, flowseal_fetch=flow_sample)
    assert applied['official_entries'] >= 200
    text = system_hosts.read_text(encoding='utf-8')
    assert 'discord.com' in text and 'github.com' in text
    assert 'sample0.example.com' in text
    assert hosts.status_hosts_only(path=system_hosts, journal_path=journal)
    assert hosts.restore_hosts_only(path=system_hosts, journal_path=journal)
    assert system_hosts.read_text(encoding='utf-8') == original
    assert not journal.exists()


def test_bad_flowseal_feed_does_not_change_hosts(tmp_path):
    file = tmp_path / 'hosts'
    file.write_text('127.0.0.1 localhost\n', encoding='utf-8')
    with pytest.raises(ValueError):
        hosts.enable_hosts_only(
            path=file, journal_path=tmp_path/'journal.json',
            geo_fetch=geo_sample, flowseal_fetch=lambda: 'not a hosts list')
    assert file.read_text(encoding='utf-8') == '127.0.0.1 localhost\n'


def test_unified_default_uses_hosts_only_instead_of_adapter_dns(tmp_path, monkeypatch):
    called = []
    monkeypatch.setattr(unified, 'save_settings', lambda setting: None)
    monkeypatch.setattr(unified, 'STATE_FILE', tmp_path/'dns.json')
    monkeypatch.setattr(unified, 'DOH_STATE_FILE', tmp_path/'doh.json')
    monkeypatch.setattr(unified, 'enable_hosts_only', lambda: called.append('hosts'))
    monkeypatch.setattr(unified, 'restore_hosts_only', lambda: called.append('remove') or True)
    monkeypatch.setattr(unified, 'status_hosts_only', lambda: True)
    setting = Settings(connect_dpi=False, connect_telegram=False,
                       connect_dns=True, launch_at_startup=False)
    controller = unified.UnifiedController(setting)
    assert controller.connect().overall == 'connected'
    assert called == ['hosts']
    assert controller.runtime_health().dns == 'on'
    assert controller.disconnect().overall == 'off'
    assert called == ['hosts', 'remove']


def test_old_adapter_backup_blocks_new_host_activation(tmp_path, monkeypatch):
    monkeypatch.setattr(unified, 'save_settings', lambda setting: None)
    backup = tmp_path/'adapter.json'
    backup.write_text('old', encoding='utf-8')
    monkeypatch.setattr(unified, 'STATE_FILE', backup)
    monkeypatch.setattr(unified, 'DOH_STATE_FILE', tmp_path/'doh.json')
    setting = Settings(connect_dpi=False, connect_telegram=False,
                       connect_dns=True, launch_at_startup=False)
    controller = unified.UnifiedController(setting)
    result = controller.connect()
    assert result.dns == 'error'
    assert 'восстановите DNS' in result.detail
