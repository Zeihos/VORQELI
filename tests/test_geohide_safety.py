from pathlib import Path
import pytest
from vorqeli_connect import geohide


def test_backup_rejects_powershell_injection():
    malicious = '1.1.1.1\');Start-Process evil.exe;#'
    with pytest.raises(ValueError):
        geohide._validate_state([{'index': 2, 'manual': malicious, 'before': []}])


def test_apply_rejects_invalid_addresses(monkeypatch):
    emitted = []
    monkeypatch.setattr(geohide, '_ps', lambda cmd: emitted.append(cmd))
    with pytest.raises(ValueError):
        geohide._apply_one(4, ['8.8.8.8', '$(whoami)'])
    assert not emitted


def test_backup_rejects_repeated_adapter():
    item = {'index': 2, 'manual': '', 'before': ['8.8.8.8']}
    with pytest.raises(ValueError):
        geohide._validate_state([item, item])


def test_ipv4_manual_dns_parsing():
    assert geohide._manual_addresses('8.8.8.8, 1.1.1.1') == ['8.8.8.8', '1.1.1.1']
