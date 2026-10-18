"""Release gate regressions: offline only, never change host DNS/registry."""
import hashlib
import json
import os
from pathlib import Path

import pytest

from vorqeli_connect.uninstall_safety import cleanup_for_uninstall, startup_cleanup_confirmed
from scripts.verify_build_manifest import verify


def _manifest(root: Path, names: dict[str, bytes]):
    for name, contents in names.items():
        file = root / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(contents)
    data = {'file_count': len(names), 'files': {
        name: {'bytes': len(contents), 'sha256': hashlib.sha256(contents).hexdigest()}
        for name, contents in names.items()
    }}
    (root / 'BUILD_MANIFEST.json').write_text(json.dumps(data), encoding='utf-8')


@pytest.mark.parametrize(('status', 'windows', 'expected'), [
    ('missing', True, True), ('registry', True, False), ('task', True, False),
    ('conflict', True, False), ('untrusted', True, False), ('unknown', True, False),
    ('disabled', True, False), ('unsupported', True, False), ('unsupported', False, True),
    ('missing', False, False),
])
def test_independent_startup_audit_is_fail_closed(status, windows, expected):
    assert startup_cleanup_confirmed(status, windows=windows) is expected


def test_uninstall_rejects_unconfirmed_startup_disable(tmp_path):
    calls = []
    result = cleanup_for_uninstall(
        check_running=lambda: False,
        disable_startup=lambda enabled: 'registry',
        audit_startup=lambda: calls.append('audit') or 'unsupported',
        backup=tmp_path / 'no-dns.json',
    )
    assert not result.success
    assert calls == []
    assert 'автозапуск' in result.details[0]


def test_uninstall_rejects_unknown_audit_even_after_disabled(tmp_path):
    result = cleanup_for_uninstall(
        check_running=lambda: False,
        disable_startup=lambda enabled: 'disabled',
        audit_startup=lambda: 'unknown',
        backup=tmp_path / 'no-dns.json',
    )
    assert not result.success
    assert 'автозапуск' in result.details[0]


def test_uninstall_restores_dns_even_when_audit_fails(tmp_path):
    backup = tmp_path / 'dns.json'
    backup.write_text('saved', encoding='utf8')
    calls=[]
    def restore():
        calls.append('dns')
        backup.unlink()
        return True
    result = cleanup_for_uninstall(check_running=lambda: False,
        disable_startup=lambda _: 'disabled', audit_startup=lambda: 'registry',
        restore=restore, backup=backup)
    assert not result.success and calls == ['dns']
    assert not backup.exists()


def test_manifest_rejects_unlisted_executable_source(tmp_path):
    _manifest(tmp_path, {'src/vorqeli_connect/app.py': b'print(1)'})
    extra = tmp_path / 'src/vorqeli_connect/hidden.py'
    extra.write_bytes(b'print("unaudited")')
    assert any('Unmanifested project file' in problem for problem in verify(tmp_path))


def test_manifest_rejects_changed_case_windows_duplicate(tmp_path):
    _manifest(tmp_path, {'src/module.py': b'a', 'src/MODULE.py': b'b'})
    assert any('case-conflicting' in problem for problem in verify(tmp_path))


def test_manifest_rejects_unexpected_windows_separator(tmp_path):
    data={'file_count':1,'files':{'src\\unsafe.py':{'bytes':0,'sha256':'0'*64}}}
    (tmp_path/'BUILD_MANIFEST.json').write_text(json.dumps(data),encoding='utf-8')
    assert any('Unsafe filename' in problem for problem in verify(tmp_path))


def test_manifest_rejects_symlinked_parent_directory(tmp_path):
    _manifest(tmp_path, {'src/mod.py': b'hello'})
    real=tmp_path/'src'
    renamed=tmp_path/'real_src'
    real.rename(renamed)
    try:
        real.symlink_to(renamed, target_is_directory=True)
    except OSError:
        pytest.skip('Symlinks unavailable')
    assert any('Linked file or directory' in problem for problem in verify(tmp_path))


def test_manifest_rejects_invalid_metadata(tmp_path):
    _manifest(tmp_path, {'src/mod.py': b'hello'})
    data=json.loads((tmp_path/'BUILD_MANIFEST.json').read_text())
    data['files']['src/mod.py']['bytes']=True
    (tmp_path/'BUILD_MANIFEST.json').write_text(json.dumps(data))
    assert any('Invalid file metadata' in problem for problem in verify(tmp_path))


def test_manifest_ignores_generated_python_cache(tmp_path):
    _manifest(tmp_path, {'src/mod.py': b'hello'})
    cache=tmp_path/'src/__pycache__'
    cache.mkdir()
    (cache/'mod.cpython-313.pyc').write_bytes(b'temporary')
    assert verify(tmp_path)==[]
