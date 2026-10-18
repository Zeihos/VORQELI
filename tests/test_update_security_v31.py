"""v0.31 fail-closed download destination tests; no network required."""
from pathlib import Path
import hashlib
import io
import pytest
from vorqeli_connect import update_checker as up

PAYLOAD = b'not an executable'
RELEASE = up.Release('0.31.0','v0.31.0',
    'https://github.com/Zeihos/VORQELI/releases/tag/v0.31.0',
    'https://github.com/Zeihos/VORQELI/releases/download/v0.31.0/VORQELI-Connect-Setup.exe',
    hashlib.sha256(PAYLOAD).hexdigest(),len(PAYLOAD))


def fake_source(*args, **kwargs):
    return io.BytesIO(PAYLOAD)


def test_nested_symlink_directory_rejected(tmp_path):
    real = tmp_path / 'real'
    real.mkdir()
    alias = tmp_path / 'alias'
    try:
        alias.symlink_to(real, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip('Symlink unavailable')
    with pytest.raises(up.UpdateError, match='символической'):
        up.download_verified(RELEASE, alias / 'nested' / 'updates', open_url=fake_source)
    assert list(real.iterdir()) == []


def test_filename_instead_of_parent_directory_rejected(tmp_path):
    parent = tmp_path / 'not-a-directory'
    parent.write_bytes(b'kept')
    with pytest.raises(up.UpdateError, match='вместо папки'):
        up.download_verified(RELEASE, parent / 'updates', open_url=fake_source)
    assert parent.read_bytes() == b'kept'


def test_normal_nested_directory_allowed(tmp_path):
    destination = up.download_verified(RELEASE, tmp_path/'a'/'b', open_url=fake_source)
    assert destination.read_bytes() == PAYLOAD
    assert destination.parent == tmp_path/'a'/'b'


def test_existing_verified_installer_reused_without_transport(tmp_path):
    previous = up.download_verified(RELEASE, tmp_path, open_url=fake_source)
    def reject_transport(*args, **kwargs):
        raise AssertionError('Verified existing installer must be reused')
    assert up.download_verified(RELEASE,tmp_path,open_url=reject_transport) == previous
