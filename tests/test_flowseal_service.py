"""Offline tests for Flowseal IPSet modes and update settings."""
from pathlib import Path
import pytest

from vorqeli_connect.flowseal_service import (
    prepare_ipset_override, IPSET_NONE_CIDR, is_newer_flowseal,
)
from vorqeli_connect.config import Settings, load_settings, save_settings
from vorqeli_connect.flowseal_alts import build_alt_arguments, alt_filename


@pytest.mark.parametrize('mode,expected', [
    ('any', b''),
    ('none', (IPSET_NONE_CIDR + '\n').encode('ascii')),
])
def test_ipset_synthetic_lists_outside_engine(tmp_path, mode, expected):
    folder = tmp_path / 'private-data'
    path = prepare_ipset_override(mode, folder)
    assert path.parent == folder
    assert path.read_bytes() == expected
    assert prepare_ipset_override(mode, folder).read_bytes() == expected


def test_loaded_keeps_verified_upstream_list(tmp_path):
    assert prepare_ipset_override('loaded', tmp_path / 'not-created') is None
    assert not (tmp_path / 'not-created').exists()


def test_ipset_rejects_invalid_mode_or_link(tmp_path):
    with pytest.raises(ValueError):
        prepare_ipset_override('invalid', tmp_path)
    root = tmp_path / 'root'
    root.mkdir()
    target = root / 'ipset-none.txt'
    real = tmp_path / 'real.txt'
    real.write_text('untouched')
    try:
        target.symlink_to(real)
    except (OSError, NotImplementedError):
        pytest.skip('Symlinks not supported by this test environment')
    with pytest.raises(ValueError):
        prepare_ipset_override('none', root)
    assert real.read_text() == 'untouched'


def test_ipset_settings_survive_restart(tmp_path):
    path = tmp_path / 'prefs.json'
    save_settings(Settings(ipset_mode='none', flowseal_update_check=False), path)
    settings = load_settings(path)
    assert settings.ipset_mode == 'none'
    assert settings.flowseal_update_check is False


def test_update_check_is_version_comparison_only():
    assert is_newer_flowseal('1.10.4', '1.10.3')
    assert not is_newer_flowseal('1.10.3', '1.10.3')
    assert not is_newer_flowseal('1.9.9', '1.10.3')
    with pytest.raises(ValueError):
        is_newer_flowseal('1.10.4;echo hacked', '1.10.3')


def test_alt_ipset_uses_isolated_list_not_original_bundle(tmp_path):
    root = tmp_path / 'bundle'
    (root / 'bin').mkdir(parents=True)
    (root / 'lists').mkdir()
    (root / 'bin/winws.exe').write_bytes(b'winws')
    (root / 'lists/ipset-all.txt').write_text('1.1.1.1')
    (root / 'lists/list-general.txt').write_text('discord.com')
    (root / 'LICENSE.txt').write_text('license')
    (root / alt_filename('alt2')).write_text(
        '@echo off\n'
        'start "zapret: %~n0" /min "%BIN%winws.exe" '
        '--wf-tcp=80,443 --filter-tcp=80,443 '
        '--ipset="%LISTS%ipset-all.txt" --dpi-desync=fake\n',
        encoding='utf-8')
    override = prepare_ipset_override('none', tmp_path / 'private')
    args = build_alt_arguments(root, 'alt2', ipset_override=override)
    assert '--ipset=' + str(override) in args
    assert '--ipset=' + str(root / 'lists/ipset-all.txt') not in args
    assert (root / 'lists/ipset-all.txt').read_text() == '1.1.1.1'
