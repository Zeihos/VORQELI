"""v0.21.0 regression tests for fail-closed config and verified DNS effects."""
import json
import pytest
from vorqeli_connect import config, geohide
from vorqeli_connect.config import Settings, save_settings, load_settings


def _adapter(index, addresses, *, manual=''):
    return {'index': index, 'alias': f'Adapter-{index}',
            'manual': manual, 'before': list(addresses)}


def test_valid_primary_preserves_intent(tmp_path):
    path = tmp_path / 'settings.json'
    save_settings(Settings(desired_enabled=True), path)
    assert load_settings(path).desired_enabled is True


def test_corrupt_primary_never_restores_old_on_intent(tmp_path):
    path = tmp_path / 'settings.json'
    save_settings(Settings(desired_enabled=True, connect_dns=False), path)
    save_settings(Settings(desired_enabled=False, connect_dns=True), path)
    path.write_text('invalid {', encoding='utf-8')
    recovered = load_settings(path)
    assert recovered.desired_enabled is False
    assert recovered.connect_dns is False  # Other preferences retained.


def test_missing_primary_backup_on_is_fail_closed(tmp_path):
    path = tmp_path / 'settings.json'
    path.with_suffix('.bak').write_text(json.dumps({
        'desired_enabled': True, 'launch_at_startup': True,
        'connect_dpi': False, 'connect_dns': True,
    }), encoding='utf-8')
    recovered = load_settings(path)
    assert not recovered.desired_enabled
    assert recovered.launch_at_startup
    assert not recovered.connect_dpi


def test_corrupt_primary_backup_keeps_telegram_secret(tmp_path, monkeypatch):
    path = tmp_path / 'settings.json'
    monkeypatch.setattr(config, 'deserialize_secret', lambda data: data.get('telegram_secret', ''))
    path.with_suffix('.bak').write_text(json.dumps({
        'desired_enabled': True, 'telegram_secret': 'a'*32,
    }), encoding='utf-8')
    path.write_text('invalid', encoding='utf-8')
    recovered = load_settings(path)
    assert not recovered.desired_enabled
    assert recovered.telegram_secret == 'a'*32


def test_dns_enable_acks_without_effect_rolls_back(tmp_path, monkeypatch):
    path = tmp_path / 'restore.json'
    state = [_adapter(4, ['1.1.1.1'], manual='1.1.1.1')]
    calls = []
    monkeypatch.setattr(geohide, 'query_dns_state', lambda: state)
    monkeypatch.setattr(geohide, '_apply_one', lambda i, ips: calls.append((i, ips)))
    with pytest.raises(RuntimeError, match='не подтвердил применение'):
        geohide.enable_dns(path, probe=False)
    assert calls == [(4, list(geohide.GEOHIDE_IPV4))]
    assert not path.exists()  # Nothing was changed, so no rollback is required.


def test_dns_enable_confirms_every_adapter(tmp_path, monkeypatch):
    path = tmp_path / 'restore.json'
    state = {4: ['1.1.1.1'], 5: ['8.8.8.8']}
    original = {key: value[:] for key, value in state.items()}
    calls = []
    monkeypatch.setattr(geohide, 'query_dns_state', lambda: [
        _adapter(idx, ips, manual=','.join(original[idx])) for idx, ips in state.items()])
    def apply(idx, ips):
        calls.append(idx)
        state[idx] = list(ips or original[idx])
    monkeypatch.setattr(geohide, '_apply_one', apply)
    assert geohide.enable_dns(path, probe=False) == 2
    assert state == {4:list(geohide.GEOHIDE_IPV4),5:list(geohide.GEOHIDE_IPV4)}
    assert calls == [4,5]
    assert path.is_file()


def test_dns_enable_partial_silent_failure_rolls_back(tmp_path, monkeypatch):
    path = tmp_path / 'restore.json'
    state = {4: ['1.1.1.1'], 5: ['8.8.8.8']}
    original = {key: value[:] for key, value in state.items()}
    monkeypatch.setattr(geohide, 'query_dns_state', lambda: [
        _adapter(idx, ips, manual=','.join(original[idx])) for idx, ips in state.items()])
    def apply(idx, ips):
        if idx == 4 or ips == original[5]:
            state[idx] = list(ips)
        # Windows acknowledged 5, but never actually changed its DNS.
    monkeypatch.setattr(geohide, '_apply_one', apply)
    with pytest.raises(RuntimeError, match='не подтвердил применение'):
        geohide.enable_dns(path, probe=False)
    assert state == original
    assert not path.exists()


def test_dns_restore_does_not_discard_unverified_snapshot(tmp_path, monkeypatch):
    path = tmp_path / 'restore.json'
    geohide._save_state([_adapter(4, ['1.1.1.1'], manual='1.1.1.1')], path)
    state = [_adapter(4, list(geohide.GEOHIDE_IPV4))]
    monkeypatch.setattr(geohide, 'query_dns_state', lambda: state)
    monkeypatch.setattr(geohide, '_apply_one', lambda *a: None)  # Silent no-op.
    with pytest.raises(RuntimeError, match='не подтвердил восстановление'):
        geohide.restore_dns(path)
    assert path.exists()
    assert json.loads(path.read_text(encoding='utf-8'))['interfaces'][0]['index'] == 4


def test_dns_restore_discards_only_verified_entries(tmp_path, monkeypatch):
    path = tmp_path / 'restore.json'
    geohide._save_state([
        _adapter(4, ['1.1.1.1'], manual='1.1.1.1'),
        _adapter(5, ['8.8.8.8'], manual='8.8.8.8'),
    ], path)
    state = {4:list(geohide.GEOHIDE_IPV4), 5:list(geohide.GEOHIDE_IPV4)}
    monkeypatch.setattr(geohide, 'query_dns_state', lambda: [
        _adapter(idx, ips) for idx, ips in state.items()])
    def apply(idx, ips):
        if idx == 4: state[idx] = list(ips)
    monkeypatch.setattr(geohide, '_apply_one', apply)
    with pytest.raises(RuntimeError, match='не полностью'):
        geohide.restore_dns(path)
    assert state[4] == ['1.1.1.1']
    assert [a['index'] for a in json.loads(path.read_text(encoding='utf-8'))['interfaces']] == [5]


def test_dns_restore_dhcp_does_not_require_old_address(tmp_path, monkeypatch):
    path = tmp_path / 'restore.json'
    geohide._save_state([_adapter(4, ['1.1.1.1'])], path)
    state = {4:list(geohide.GEOHIDE_IPV4)}
    monkeypatch.setattr(geohide, 'query_dns_state', lambda: [
        _adapter(idx, ips) for idx, ips in state.items()])
    monkeypatch.setattr(geohide, '_apply_one', lambda idx, ips: state.__setitem__(idx,['9.9.9.9']))
    assert geohide.restore_dns(path)
    assert not path.exists()


def test_dns_restore_postcheck_failure_keeps_backup(tmp_path, monkeypatch):
    path = tmp_path / 'restore.json'
    geohide._save_state([_adapter(4, ['1.1.1.1'], manual='1.1.1.1')], path)
    count = [0]
    def query():
        count[0] += 1
        if count[0] > 1:
            raise OSError('network API unavailable')
        return [_adapter(4,list(geohide.GEOHIDE_IPV4))]
    monkeypatch.setattr(geohide,'query_dns_state', query)
    monkeypatch.setattr(geohide,'_apply_one',lambda *a:None)
    with pytest.raises(RuntimeError,match='Не удалось проверить'):
        geohide.restore_dns(path)
    assert path.exists()


def test_dns_failed_apply_rollback_noop_keeps_backup(tmp_path, monkeypatch):
    path = tmp_path / 'restore.json'
    current_ips = ['1.1.1.1']
    times = [0]
    def query():
        times[0] += 1
        return [_adapter(4, current_ips, manual='1.1.1.1')]
    def apply(idx, ips):
        if ips == list(geohide.GEOHIDE_IPV4):
            current_ips[:] = list(geohide.GEOHIDE_IPV4)
            raise RuntimeError('driver error after partial apply')
        # Restoration command succeeds but does not change anything.
    monkeypatch.setattr(geohide, 'query_dns_state', query)
    monkeypatch.setattr(geohide, '_apply_one', apply)
    with pytest.raises(RuntimeError, match='Восстановление не завершено'):
        geohide.enable_dns(path, probe=False)
    assert path.is_file()
    assert current_ips == list(geohide.GEOHIDE_IPV4)
