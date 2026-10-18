"""Failure-injection tests for durable explicit OFF intent (no Windows/network calls)."""
import json
from pathlib import Path

import pytest

from vorqeli_connect.config import Settings, load_settings, off_intent_path, save_settings


def test_off_first_write_creates_durable_marker(tmp_path):
    p = tmp_path / 'settings.json'
    save_settings(Settings(desired_enabled=False), p)
    assert off_intent_path(p).read_bytes() == b'OFF\n'
    assert load_settings(p).desired_enabled is False


def test_on_request_removes_guard_only_after_success(tmp_path):
    p = tmp_path / 'settings.json'
    save_settings(Settings(desired_enabled=False), p)
    save_settings(Settings(desired_enabled=True), p)
    assert not off_intent_path(p).exists()
    assert load_settings(p).desired_enabled is True


def test_guard_overrides_stale_on_json_after_interrupted_off(tmp_path, monkeypatch):
    p = tmp_path / 'settings.json'
    save_settings(Settings(desired_enabled=True), p)
    original_replace = Path.replace

    def interrupt(self, target):
        if self == p.with_suffix('.tmp'):
            raise OSError('simulated power loss during settings replace')
        return original_replace(self, target)

    monkeypatch.setattr(Path, 'replace', interrupt)
    with pytest.raises(OSError, match='power loss'):
        save_settings(Settings(desired_enabled=False), p)
    # The primary file still reports the old ON; the independent guard wins.
    assert json.loads(p.read_text())['desired_enabled'] is True
    assert off_intent_path(p).is_file()
    assert load_settings(p).desired_enabled is False


def test_recovered_on_backup_is_overridden_by_guard(tmp_path):
    p = tmp_path / 'settings.json'
    save_settings(Settings(desired_enabled=True), p)
    off_intent_path(p).write_bytes(b'OFF\n')
    p.with_suffix('.bak').write_text('{"desired_enabled": true}', encoding='utf-8')
    p.write_text('invalid', encoding='utf-8')
    assert not load_settings(p).desired_enabled


def test_interrupted_on_save_does_not_clear_guard(tmp_path, monkeypatch):
    p = tmp_path / 'settings.json'
    save_settings(Settings(desired_enabled=False), p)
    original_replace = Path.replace
    def interrupt(self, target):
        if self == p.with_suffix('.tmp'):
            raise OSError('interrupted ON write')
        return original_replace(self, target)
    monkeypatch.setattr(Path, 'replace', interrupt)
    with pytest.raises(OSError, match='interrupted ON'):
        save_settings(Settings(desired_enabled=True), p)
    assert off_intent_path(p).exists()
    assert not load_settings(p).desired_enabled


def test_failing_off_marker_aborts_settings_write(tmp_path, monkeypatch):
    from vorqeli_connect import config
    p = tmp_path / 'settings.json'
    save_settings(Settings(desired_enabled=True), p)
    before = p.read_bytes()
    monkeypatch.setattr(config, '_persist_off_intent', lambda path: (_ for _ in ()).throw(OSError('readonly')))
    with pytest.raises(OSError, match='readonly'):
        save_settings(Settings(desired_enabled=False), p)
    assert p.read_bytes() == before  # No promise that OFF persisted.


def test_broken_symlink_guard_fails_closed(tmp_path):
    p = tmp_path / 'settings.json'
    save_settings(Settings(desired_enabled=True), p)
    off_intent_path(p).symlink_to(tmp_path / 'nonexistent-file')
    assert not load_settings(p).desired_enabled


def test_explicit_on_after_prior_off_guard_recovers(tmp_path):
    p = tmp_path / 'settings.json'
    save_settings(Settings(desired_enabled=True), p)
    save_settings(Settings(desired_enabled=False), p)
    save_settings(Settings(desired_enabled=True), p)
    assert load_settings(p).desired_enabled
    assert not off_intent_path(p).exists()


def test_off_guard_is_scoped_to_the_settings_file(tmp_path):
    p = tmp_path / 'one.json'
    q = tmp_path / 'two.json'
    save_settings(Settings(desired_enabled=False), p)
    save_settings(Settings(desired_enabled=True), q)
    assert load_settings(p).desired_enabled is False
    assert load_settings(q).desired_enabled is True


def test_guard_survives_corruption_without_exposing_secrets(tmp_path):
    p = tmp_path / 'settings.json'
    save_settings(Settings(desired_enabled=False), p)
    p.write_bytes(b'not-json')
    assert load_settings(p).desired_enabled is False
    assert b'secret' not in off_intent_path(p).read_bytes()


def test_doctor_reports_boolean_guard_only():
    from vorqeli_connect.doctor import create_report
    kw = dict(is_windows=True, admin=False, tray_available=True,
              telegram_available=True, dpi_available=False, dns_backup_present=False)
    report = create_report(Settings(), off_intent_guard=True, **kw)
    assert report['explicit_off_guard'] is True
    report = create_report(Settings(), off_intent_guard=False, **kw)
    assert report['explicit_off_guard'] is False
    assert not any('.off-intent' in str(v) for v in report.values())


def test_ui_version_uses_the_same_package_version():
    from vorqeli_connect import __version__
    from vorqeli_connect.app import VERSION
    assert VERSION == __version__
