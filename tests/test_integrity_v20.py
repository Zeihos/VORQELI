"""Regression tests: cached binaries and offline doctor integrity."""
import hashlib
import io
import json
import zipfile
from pathlib import Path
from vorqeli_connect import assets_manager as assets, doctor
from vorqeli_connect.config import Settings


def test_verification_manifest_and_modification(tmp_path):
    root=tmp_path/'engine'
    (root/'bin').mkdir(parents=True)
    (root/'bin/winws.exe').write_bytes(b'known executable')
    (root/'bin/WinDivert64.sys').write_bytes(b'driver')
    assets.write_engine_manifest(root,release_sha='a'*64)
    assert assets.engine_integrity(root,release_sha='a'*64)=='verified'
    (root/'bin/winws.exe').write_bytes(b'modified executable')
    assert assets.engine_integrity(root,release_sha='a'*64)=='tampered'


def test_manifest_missing_is_legacy(tmp_path):
    root=tmp_path/'legacy'
    (root/'bin').mkdir(parents=True)
    (root/'bin/winws.exe').write_bytes(b'old binary')
    assert assets.engine_integrity(root)=='legacy'
    assert assets.engine_integrity(tmp_path/'absent')=='missing'


def test_extra_binary_is_detected(tmp_path):
    root=tmp_path/'engine'
    (root/'bin').mkdir(parents=True)
    (root/'bin/winws.exe').write_bytes(b'original')
    assets.write_engine_manifest(root)
    (root/'bin/injected.dll').write_bytes(b'evil')
    assert assets.engine_integrity(root)=='tampered'


def test_wrong_release_hash_is_rejected(tmp_path):
    root=tmp_path/'engine'
    (root/'bin').mkdir(parents=True)
    (root/'bin/winws.exe').write_bytes(b'original')
    assets.write_engine_manifest(root, release_sha='f'*64)
    assert assets.engine_integrity(root, release_sha='0'*64)=='tampered'


def test_invalid_manifest_no_crash(tmp_path):
    root=tmp_path/'engine'
    root.mkdir()
    (root/assets.ENGINE_MANIFEST).write_text('{broken',encoding='utf-8')
    assert assets.engine_integrity(root)=='tampered'


def test_doctor_only_reports_enum(tmp_path):
    report=doctor.create_report(Settings(),is_windows=True,admin=False,
        tray_available=True,telegram_available=True,dpi_available=False,
        dns_backup_present=False,dpi_integrity='tampered')
    assert report['dpi_integrity']=='tampered'
    assert 'secret' not in json.dumps(report).lower().replace('telegram_secret_status','') or report['telegram_secret_status'] == 'missing'
    assert report['schema']==1


def test_failed_reinstall_preserves_legacy_cache(tmp_path,monkeypatch):
    root=tmp_path/'engines'/'zapret-1.10.3'
    (root/'bin').mkdir(parents=True)
    (root/'bin/winws.exe').write_bytes(b'keep old')
    (root/'lists').mkdir()
    (root/'lists/list-general.txt').write_text('example.com')
    (root/'LICENSE.txt').write_text('MIT')
    class Response(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self,*args): self.close()
    monkeypatch.setattr(assets.urllib.request,'urlopen', lambda *args,**kwargs:Response(b'not official'))
    import pytest
    with pytest.raises(ValueError, match='контрольная сумма'):
        assets.ensure_zapret(base_dir=tmp_path/'engines')
    assert (root/'bin/winws.exe').read_bytes()==b'keep old'


def test_verified_cache_is_offline(tmp_path,monkeypatch):
    root=tmp_path/'engines'/'zapret-1.10.3'
    (root/'bin').mkdir(parents=True)
    (root/'lists').mkdir()
    (root/'bin/winws.exe').write_bytes(b'original')
    (root/'lists/list-general.txt').write_text('example.com')
    (root/'LICENSE.txt').write_text('MIT')
    assets.write_engine_manifest(root)
    monkeypatch.setattr(assets.urllib.request,'urlopen', lambda *args,**kwargs:(_ for _ in ()).throw(AssertionError('unexpected download')))
    assert assets.ensure_zapret(base_dir=tmp_path/'engines')==root
