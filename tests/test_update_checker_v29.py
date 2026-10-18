"""Offline update security regression tests: no internet or actual EXE execution."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import pytest
from vorqeli_connect import update_checker as u

GOOD = b'VORQELI-test-installer-content'
HASH = hashlib.sha256(GOOD).hexdigest()


class Response(io.BytesIO):
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.close()


def release_json(*, tag='v0.30.0', asset=None, draft=False, prerelease=False):
    if asset is None:
        asset = {
            'name': u.INSTALLER_ASSET, 'size': len(GOOD), 'digest': 'sha256:'+HASH,
            'browser_download_url': f'https://github.com/Zeihos/VORQELI/releases/download/{tag}/{u.INSTALLER_ASSET}',
        }
    return {'tag_name': tag, 'draft': draft, 'prerelease': prerelease, 'assets': [asset]}


def fake_metadata(data):
    return lambda request, timeout: Response(json.dumps(data).encode())


def test_newer_release_with_verified_hash():
    release = u.check_for_update('0.29.0', open_url=fake_metadata(release_json()))
    assert release.version == '0.30.0'
    assert release.tag == 'v0.30.0'
    assert release.sha256 == HASH
    assert release.size == len(GOOD)
    assert release.html_url.startswith('https://github.com/Zeihos/VORQELI/releases/tag/')


def test_tag_without_v_supported(tmp_path):
    release = u.check_for_update('0.29.0', open_url=fake_metadata(release_json(tag='0.30.0')))
    assert release.tag == '0.30.0'
    assert u.download_verified(release, tmp_path, open_url=lambda *_ ,**__: Response(GOOD))


def test_up_to_date_does_not_require_asset():
    data=release_json()
    del data['assets']
    assert u.check_for_update('0.30.0',open_url=fake_metadata(data)) is None


@pytest.mark.parametrize('current,latest',[
    ('0.30.0','v0.29.0'), ('0.30.0','v0.30.0'), ('1.0.0','v0.99.99')
])
def test_no_downgrades(current,latest):
    assert u.check_for_update(current,open_url=fake_metadata(release_json(tag=latest))) is None


@pytest.mark.parametrize('value',[
    '', 'v1.0','1.0.0.0','v01.0.0','v1.0.0+evil','1.0.0-rc1',
    '../../x','v1.0.0\nfoo','v99999.0.0',{},None
])
def test_invalid_version_rejected(value):
    with pytest.raises(u.UpdateError):
        u.parse_version(value)


@pytest.mark.parametrize('field', ['draft','prerelease'])
def test_rejects_unpublished_release(field):
    data=release_json()
    data[field]=True
    with pytest.raises(u.UpdateError,match='неопубликованный'):
        u.check_for_update('0.29.0',open_url=fake_metadata(data))


def test_rejects_missing_release_flags():
    data=release_json(); data.pop('draft')
    with pytest.raises(u.UpdateError):
        u.check_for_update('0.29.0',open_url=fake_metadata(data))


@pytest.mark.parametrize('bad_url',[
    'http://github.com/Zeihos/VORQELI/releases/download/v0.30.0/VORQELI-Connect-Setup.exe',
    'https://github.com.evil.tld/Zeihos/VORQELI/releases/download/v0.30.0/VORQELI-Connect-Setup.exe',
    'https://evil.tld/file.exe',
    'https://github.com/Zeihos/VORQELI/releases/download/v0.30.0/other.exe',
    'https://github.com/Zeihos/VORQELI/releases/download/v0.30.0/VORQELI-Connect-Setup.exe?ref=evil',
    'https://github.com/Zeihos/VORQELI/releases/download/v0.30.0/../VORQELI-Connect-Setup.exe',
    'https://github.com@evil.tld/Zeihos/VORQELI/releases/download/v0.30.0/VORQELI-Connect-Setup.exe',
])
def test_rejects_untrusted_download_url(bad_url):
    asset = release_json()['assets'][0]
    asset['browser_download_url'] = bad_url
    with pytest.raises(u.UpdateError,match='Неофициальная'):
        u.check_for_update('0.29.0',open_url=fake_metadata(release_json(asset=asset)))


@pytest.mark.parametrize('digest', [None,'','sha1:'+HASH,'sha256:1234',HASH])
def test_rejects_missing_digest(digest):
    asset = release_json()['assets'][0]
    asset['digest'] = digest
    with pytest.raises(u.UpdateError,match='SHA-256'):
        u.check_for_update('0.29.0',open_url=fake_metadata(release_json(asset=asset)))


@pytest.mark.parametrize('size',[0,-5,'30',u.MAX_DOWNLOAD+1,True])
def test_rejects_invalid_size(size):
    asset = release_json()['assets'][0]
    asset['size'] = size
    with pytest.raises(u.UpdateError,match='размер'):
        u.check_for_update('0.29.0',open_url=fake_metadata(release_json(asset=asset)))


def test_duplicate_installers_rejected():
    data=release_json();data['assets'].append(data['assets'][0].copy())
    with pytest.raises(u.UpdateError,match='единственный'):
        u.check_for_update('0.29.0',open_url=fake_metadata(data))


def test_max_metadata_enforced():
    data=release_json();data['notes']='X'*(u.MAX_METADATA+1)
    with pytest.raises(u.UpdateError,match='большой'):
        u.check_for_update('0.29.0',open_url=fake_metadata(data))


def test_malformed_metadata_rejected():
    with pytest.raises(u.UpdateError,match='Некорректные'):
        u.check_for_update('0.29.0',open_url=lambda *_ ,**__: Response(b'garbage'))


def test_no_network_on_import():
    assert u.API_URL=='https://api.github.com/repos/Zeihos/VORQELI/releases/latest'


def test_valid_download_and_reuse_verified(tmp_path):
    release=u.check_for_update('0.29.0',open_url=fake_metadata(release_json()))
    calls=[]
    def open_asset(req,timeout):
        calls.append(req.full_url)
        return Response(GOOD)
    result=u.download_verified(release,tmp_path,open_url=open_asset)
    assert result.is_file() and result.read_bytes()==GOOD
    assert calls==[release.installer_url]
    # A second attempt checks file hash; no duplicate network request.
    assert u.download_verified(release,tmp_path,open_url=open_asset)==result
    assert len(calls)==1
    assert list(tmp_path.glob('*.part'))==[]


@pytest.mark.parametrize('payload', [GOOD[:-2],GOOD+b'junk',b'X'*len(GOOD)])
def test_corrupted_download_not_published(tmp_path,payload):
    release=u.check_for_update('0.29.0',open_url=fake_metadata(release_json()))
    with pytest.raises(u.UpdateError):
        u.download_verified(release,tmp_path,open_url=lambda *_ ,**__: Response(payload))
    assert list(tmp_path.iterdir())==[]


def test_bad_existing_installer_not_overwritten(tmp_path):
    release=u.check_for_update('0.29.0',open_url=fake_metadata(release_json()))
    existing=tmp_path/'VORQELI-Connect-Setup-v0.30.0.exe'
    existing.write_bytes(b'wrong')
    with pytest.raises(u.UpdateError,match='непроверенный'):
        u.download_verified(release,tmp_path,open_url=lambda *_ ,**__: (_ for _ in ()).throw(AssertionError('no request')))
    assert existing.read_bytes()==b'wrong'


def test_download_mismatch_tag_rejected_before_request(tmp_path):
    release=u.check_for_update('0.29.0',open_url=fake_metadata(release_json()))
    from dataclasses import replace
    with pytest.raises(u.UpdateError,match='Тег'):
        u.download_verified(replace(release,tag='v0.32.0'),tmp_path,open_url=lambda *_ ,**__: None)


def test_release_is_not_executed(tmp_path,monkeypatch):
    release=u.check_for_update('0.29.0',open_url=fake_metadata(release_json()))
    def forbidden(*args,**kwargs):
        raise AssertionError('Running binaries must never happen')
    import subprocess
    monkeypatch.setattr(subprocess,'run',forbidden)
    monkeypatch.setattr(subprocess,'Popen',forbidden)
    assert u.download_verified(release,tmp_path,open_url=lambda *_ ,**__: Response(GOOD)).exists()


def test_no_published_release_404_message():
    from urllib.error import HTTPError
    def no_release(req,timeout):
        raise HTTPError(req.full_url,404,"Not Found",{},None)
    with pytest.raises(u.UpdateError,match="нет опубликованных релизов"):
        u.check_for_update("0.29.0",open_url=no_release)
