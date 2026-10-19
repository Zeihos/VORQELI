"""Uninstall guard tests must never change the host network or registry."""
from pathlib import Path
from vorqeli_connect.uninstall_safety import cleanup_for_uninstall


def test_running_app_blocks_all_mutations(tmp_path):
    calls = []
    result = cleanup_for_uninstall(
        check_running=lambda: True,
        disable_startup=lambda x: calls.append('startup'),
        restore=lambda: calls.append('dns'),
        backup=tmp_path / 'dns.json',
    audit_startup=_audit_absent)
    assert not result.success
    assert calls == []
    assert 'трей' in result.details[0]


def test_running_check_error_blocks_all_mutations(tmp_path):
    def denied():
        raise PermissionError('denied')
    result = cleanup_for_uninstall(
        check_running=denied,
        disable_startup=lambda x: (_ for _ in ()).throw(AssertionError('should not run')),
        backup=tmp_path / 'dns.json',
    audit_startup=_audit_absent)
    assert not result.success
    assert 'Проверка' in result.details[0]


def test_clean_uninstall_without_dns_backup(tmp_path):
    called = []
    result = cleanup_for_uninstall(
        check_running=lambda: False,
        disable_startup=lambda enabled: called.append(enabled) or 'disabled',
        restore=lambda: (_ for _ in ()).throw(AssertionError('no backup exists')),
        backup=tmp_path / 'missing.json',
    audit_startup=_audit_absent)
    assert result.success and result.details == ()
    assert called == [False]


def test_dns_is_restored_before_uninstall(tmp_path):
    backup = tmp_path / 'backup.json'
    backup.write_text('backup', encoding='utf8')
    def restore():
        backup.unlink()
        return True
    result = cleanup_for_uninstall(check_running=lambda: False,
                                   disable_startup=lambda _: 'disabled',
                                   restore=restore, backup=backup, audit_startup=_audit_absent)
    assert result.success
    assert not backup.exists()


def test_dns_failed_restore_blocks_uninstall(tmp_path):
    backup = tmp_path / 'backup.json'
    backup.write_text('backup', encoding='utf8')
    result = cleanup_for_uninstall(check_running=lambda: False,
                                   disable_startup=lambda _: 'disabled',
                                   restore=lambda: False, backup=backup, audit_startup=_audit_absent)
    assert not result.success
    assert backup.exists()
    assert 'DNS' in result.details[0]


def test_false_success_when_backup_still_exists_is_rejected(tmp_path):
    backup = tmp_path / 'backup.json'
    backup.write_text('backup', encoding='utf8')
    result = cleanup_for_uninstall(check_running=lambda: False,
                                   disable_startup=lambda _: 'disabled',
                                   restore=lambda: True, backup=backup, audit_startup=_audit_absent)
    assert not result.success
    assert backup.exists()


def test_failed_startup_deletion_blocks_uninstall(tmp_path):
    result = cleanup_for_uninstall(check_running=lambda: False,
                                   disable_startup=lambda _: (_ for _ in ()).throw(OSError('access denied')),
                                   backup=tmp_path / 'missing.json', audit_startup=_audit_absent)
    assert not result.success
    assert 'автозапуск' in result.details[0]


def test_independent_dns_and_startup_cleanup_attempted(tmp_path):
    backup = tmp_path / 'backup.json'
    backup.write_text('backup', encoding='utf8')
    calls = []
    def fail_startup(_):
        calls.append('startup')
        raise OSError('no access')
    def fix_dns():
        calls.append('dns')
        backup.unlink()
        return True
    result = cleanup_for_uninstall(check_running=lambda: False,
                                   disable_startup=fail_startup,
                                   restore=fix_dns, backup=backup, audit_startup=_audit_absent)
    assert not result.success
    assert calls == ['startup','dns']
    assert not backup.exists()


def _audit_absent():
    """Mock Windows registration state, never read the actual host."""
    import os
    return 'missing' if os.name == 'nt' else 'unsupported'
