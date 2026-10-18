import json
from vorqeli_connect import secret_storage, config
from vorqeli_connect.config import Settings


def test_source_roundtrip_is_explicitly_portable(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'serialize_secret', lambda value: {'telegram_secret': value})
    path=tmp_path/'settings.json'
    secret='ab'*16
    settings=Settings(telegram_secret=secret)
    config.save_settings(settings,path)
    assert config.load_settings(path).telegram_secret==secret


def test_dpapi_config_does_not_write_plaintext(monkeypatch,tmp_path):
    # Platform-agnostic test of the JSON behavior, not a native Windows DPAPI test.
    monkeypatch.setattr(secret_storage, 'serialize_secret',
                        lambda value: {'telegram_secret_dpapi':'ENCRYPTED_TEST'} if value else {'telegram_secret':''})
    monkeypatch.setattr(config, 'serialize_secret',secret_storage.serialize_secret)
    monkeypatch.setattr(config, 'deserialize_secret',
                        lambda data:'cd'*16 if data.get('telegram_secret_dpapi') else data.get('telegram_secret',''))
    path=tmp_path/'settings.json'
    config.save_settings(Settings(telegram_secret='cd'*16),path)
    raw=path.read_text()
    assert 'cd'*16 not in raw
    assert 'ENCRYPTED_TEST' in raw
    assert config.load_settings(path).telegram_secret=='cd'*16


def test_unreadable_blob_is_not_discarded(monkeypatch,tmp_path):
    path=tmp_path/'settings.json'
    path.write_text(json.dumps({'desired_enabled':True,'launch_at_startup':False,
                               'telegram_secret_dpapi':'PROTECTED_BLOB'}))
    monkeypatch.setattr(config,'deserialize_secret',lambda data: (_ for _ in ()).throw(ValueError('Invalid DPAPI')))
    settings=config.load_settings(path)
    assert settings.desired_enabled
    assert settings.telegram_secret_error
    assert settings.telegram_secret_dpapi_blob=='PROTECTED_BLOB'
    config.save_settings(settings,path)
    assert json.loads(path.read_text())['telegram_secret_dpapi']=='PROTECTED_BLOB'


def test_invalid_encrypted_data_rejected():
    import pytest
    with pytest.raises(ValueError):
        secret_storage.unprotect('hello!')
