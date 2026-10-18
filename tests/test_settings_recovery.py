import json
from vorqeli_connect.config import Settings, load_settings, save_settings
from vorqeli_connect import config


def test_backup_created_and_recovers_corrupt_primary(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'serialize_secret', lambda value: {'telegram_secret': value})
    monkeypatch.setattr(config, 'deserialize_secret', lambda data: data.get('telegram_secret', ''))
    path = tmp_path / 'settings.json'
    save_settings(Settings(desired_enabled=True, connect_dns=False), path)
    save_settings(Settings(desired_enabled=False, connect_dns=True), path)
    assert path.with_suffix('.bak').exists()
    path.write_text('{broken json', encoding='utf-8')
    restored = load_settings(path)
    assert restored.desired_enabled is False  # Fail closed: backup may predate OFF action
    assert restored.connect_dns is False


def test_no_corrupted_file_copied_over_good_backup(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'serialize_secret', lambda value: {'telegram_secret': value})
    path = tmp_path / 'settings.json'
    save_settings(Settings(desired_enabled=True), path)
    save_settings(Settings(desired_enabled=False), path)
    original = path.with_suffix('.bak').read_bytes()
    path.write_text('broken', encoding='utf-8')
    save_settings(Settings(desired_enabled=False, connect_dns=False), path)
    assert path.with_suffix('.bak').read_bytes() == original
    assert json.loads(path.read_text(encoding='utf-8'))['connect_dns'] is False


def test_load_malformed_backup_falls_back_to_defaults(tmp_path):
    path = tmp_path / 'settings.json'
    path.write_text('not json', encoding='utf-8')
    path.with_suffix('.bak').write_text('not json either', encoding='utf-8')
    assert load_settings(path) == Settings()


def test_missing_primary_can_recover_backup(tmp_path):
    path = tmp_path / 'settings.json'
    path.with_suffix('.bak').write_text(json.dumps({'launch_at_startup': False}), encoding='utf-8')
    assert load_settings(path).launch_at_startup is False
