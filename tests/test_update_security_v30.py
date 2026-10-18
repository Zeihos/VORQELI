"""Regression tests for fail-closed HTTP redirects and atomic installer publication."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import hashlib
import io
import os
import pytest
from urllib.request import Request

from vorqeli_connect import update_checker as up

GOOD = b'fake installer only; not executable'
SHA = hashlib.sha256(GOOD).hexdigest()
URL = 'https://github.com/Zeihos/VORQELI/releases/download/v0.30.0/VORQELI-Connect-Setup.exe'
CDN = 'https://release-assets.githubusercontent.com/github-production-release-asset/100/200?sp=r&sig=abc'


class NamedResponse(io.BytesIO):
    def __init__(self, payload, url):
        super().__init__(payload)
        self.url = url
    def geturl(self):
        return self.url
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.close()


def make_release():
    return up.Release('0.30.0','v0.30.0','https://github.com/Zeihos/VORQELI/releases/tag/v0.30.0',URL,SHA,len(GOOD))


@pytest.mark.parametrize('url',[ 
    'https://attacker.example/malware.exe',
    'http://release-assets.githubusercontent.com/payload',
    'https://release-assets.githubusercontent.com.evil.tld/payload',
    'https://release-assets.githubusercontent.com:444/payload',
    'https://user:password@release-assets.githubusercontent.com/payload',
    'https://github.com.evil.tld/evil.exe',
    'https://github.com/Zeihos/VORQELI/releases/download/v0.30.0/other.exe',
    'https://release-assets.githubusercontent.com/../evil.exe',
    'https://release-assets.githubusercontent.com/file#fragment',
    'https://release-assets.githubusercontent.com/',
    'https://release-assets.githubusercontent.com:bad/path',
    'https://[malformed-host/path',
    'ftp://objects.githubusercontent.com/malware.exe',
])
def test_untrusted_asset_redirects_rejected_before_request(url):
    redirect = up._RestrictedRedirectHandler('asset',URL)
    with pytest.raises(up.UpdateError,match='перенаправление'):
        redirect.redirect_request(Request(URL),None,302,'Found',{},url)


def test_api_never_redirects_even_to_github():
    handler = up._RestrictedRedirectHandler('metadata')
    with pytest.raises(up.UpdateError):
        handler.redirect_request(Request(up.API_URL),None,302,'Found',{},up.API_URL)


def test_github_cdn_redirect_is_allowed_and_limits_hops():
    handler = up._RestrictedRedirectHandler('asset',URL)
    for i in range(3):
        r = handler.redirect_request(Request(URL),None,302,'Found',{},CDN)
        assert r.full_url == CDN
    with pytest.raises(up.UpdateError):
        handler.redirect_request(Request(URL),None,302,'Found',{},CDN)


def test_objects_github_cdn_allowed():
    assert up._redirect_allowed('https://objects.githubusercontent.com/objects/f?sig=abc',purpose='asset',original_asset_url=URL)
    assert up._redirect_allowed(URL,purpose='asset',original_asset_url=URL)


def test_metadata_rejects_redirected_response():
    with pytest.raises(up.UpdateError,match='перенаправление'):
        up.check_for_update('0.29.0',open_url=lambda *_ ,**__: NamedResponse(b'{}','https://attacker.example/fake'))


def test_reject_fake_transport_response_from_untrusted_host(tmp_path):
    with pytest.raises(up.UpdateError,match='неподтверждённого'):
        up.download_verified(make_release(),tmp_path,open_url=lambda *_ ,**__: NamedResponse(GOOD,'https://evil.tld/install.exe'))
    assert list(tmp_path.iterdir()) == []


def test_allows_response_from_github_asset_cdn(tmp_path):
    file = up.download_verified(make_release(),tmp_path,open_url=lambda *_ ,**__: NamedResponse(GOOD,CDN))
    assert file.read_bytes() == GOOD


def test_target_created_during_download_never_overwritten(tmp_path):
    release = make_release()
    target = tmp_path/'VORQELI-Connect-Setup-v0.30.0.exe'
    def competing_download(req,timeout):
        target.write_bytes(b'created by another task')
        return NamedResponse(GOOD,URL)
    with pytest.raises(up.UpdateError,match='появился'):
        up.download_verified(release,tmp_path,open_url=competing_download)
    assert target.read_bytes() == b'created by another task'
    assert len(list(tmp_path.glob('*.part'))) == 0


def test_existing_symlink_not_accepted_as_trusted_installer(tmp_path):
    elsewhere = tmp_path / 'original.exe'
    elsewhere.write_bytes(GOOD)
    symlink = tmp_path/'VORQELI-Connect-Setup-v0.30.0.exe'
    try:
        symlink.symlink_to(elsewhere)
    except (NotImplementedError, OSError):
        pytest.skip('File system does not support symlinks')
    with pytest.raises(up.UpdateError,match='непроверенный'):
        up.download_verified(make_release(),tmp_path)
    assert elsewhere.read_bytes() == GOOD


def test_symlinked_updates_directory_rejected(tmp_path):
    target = tmp_path / 'target'
    target.mkdir()
    link = tmp_path / 'link'
    try:
        link.symlink_to(target,target_is_directory=True)
    except (NotImplementedError,OSError):
        pytest.skip('File system does not support directory symlinks')
    with pytest.raises(up.UpdateError,match='символической'):
        up.download_verified(make_release(),link)


def test_link_publish_not_supporting_filesystem_fails_closed(tmp_path,monkeypatch):
    def no_link(*args):
        raise OSError('Hard link unsupported')
    monkeypatch.setattr(up.os,'link',no_link)
    with pytest.raises(up.UpdateError,match='Не удалось скачать'):
        up.download_verified(make_release(),tmp_path,open_url=lambda *_ ,**__: NamedResponse(GOOD,URL))
    assert list(tmp_path.iterdir()) == []


def test_download_remains_non_executable(tmp_path):
    result=up.download_verified(make_release(),tmp_path,open_url=lambda *_ ,**__: NamedResponse(GOOD,URL))
    assert result.name=='VORQELI-Connect-Setup-v0.30.0.exe'
    assert result.read_bytes()==GOOD
