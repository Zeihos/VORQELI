import hashlib
import io
import zipfile
from pathlib import Path
import pytest
from vorqeli_connect.assets_manager import safe_extract_zip, sha256_file, find_bundle


def make_zip(file: Path, entries: dict[str, bytes]):
    with zipfile.ZipFile(file, 'w') as z:
        for name, content in entries.items(): z.writestr(name, content)


def test_sha256(tmp_path):
    a=tmp_path/'a'
    a.write_bytes(b'hello')
    assert sha256_file(a)==hashlib.sha256(b'hello').hexdigest()


def test_zip_rejects_traversal(tmp_path):
    archive=tmp_path/'bad.zip'
    make_zip(archive, {'../../evil.txt': b'abc'})
    with pytest.raises(ValueError, match='Небезопасное'):
        safe_extract_zip(archive,tmp_path/'output')
    assert not (tmp_path/'evil.txt').exists()


def test_zip_rejects_windows_drive_escape(tmp_path):
    archive=tmp_path/'bad.zip'
    make_zip(archive, {'C:/evil.txt': b'abc'})
    with pytest.raises(ValueError):safe_extract_zip(archive,tmp_path/'output')


def test_zip_valid(tmp_path):
    archive=tmp_path/'good.zip'
    make_zip(archive, {'repo/bin/winws.exe': b'ab', 'repo/lists/list-general.txt': b'abc',
                       'repo/LICENSE.txt': b'MIT'})
    out=tmp_path/'out'
    safe_extract_zip(archive,out)
    assert find_bundle(out)==out/'repo'


def test_zip_size_limit(tmp_path,monkeypatch):
    from vorqeli_connect import assets_manager
    monkeypatch.setattr(assets_manager,'MAX_EXTRACT_BYTES',8)
    archive=tmp_path/'bad.zip'
    make_zip(archive,{'large':b'1'*50})
    with pytest.raises(ValueError):safe_extract_zip(archive,tmp_path/'out')


def test_autodownload_verified_bundle(tmp_path, monkeypatch):
    from vorqeli_connect import assets_manager as a
    import io
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w') as z:
        z.writestr('zapret/bin/winws.exe',b'engine')
        z.writestr('zapret/lists/list-general.txt',b'youtube.com')
        z.writestr('zapret/LICENSE.txt',b'MIT License')
    value=buffer.getvalue()
    class Response(io.BytesIO):
        def __enter__(self):return self
        def __exit__(self,*args):self.close()
    monkeypatch.setattr(a.urllib.request,'urlopen',lambda *args,**kwargs:Response(value))
    dest=a.ensure_zapret(base_dir=tmp_path/'engines',url='https://example.test/release.zip',
                         expected_sha=hashlib.sha256(value).hexdigest())
    assert (dest/'bin/winws.exe').read_bytes()==b'engine'
    assert a.ensure_zapret(base_dir=tmp_path/'engines')==dest


def test_autodownload_rejects_tampered_hash(tmp_path, monkeypatch):
    from vorqeli_connect import assets_manager as a
    import io
    class Response(io.BytesIO):
        def __enter__(self):return self
        def __exit__(self,*args):self.close()
    monkeypatch.setattr(a.urllib.request,'urlopen',lambda *args,**kwargs:Response(b'fake zip'))
    with pytest.raises(ValueError,match='контрольная сумма'):
        a.ensure_zapret(base_dir=tmp_path/'engines',expected_sha='0'*64)
    assert not (tmp_path/'engines'/'zapret-1.10.3').exists()
