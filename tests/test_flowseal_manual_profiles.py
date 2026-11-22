"""Offline regression: every pinned Flowseal profile is selectable and safe."""
from pathlib import Path
import pytest

from vorqeli_connect.flowseal_alts import (
    ALT_MODES, ALT_PRIORITY, EXTRA_PROFILE_FILES, profile_filename,
)
from vorqeli_connect.engine_adapters import build_dpi_spec
from vorqeli_connect.config import Settings, save_settings, load_settings
from vorqeli_connect.assets_manager import write_engine_manifest, engine_integrity


def synthetic_package(root: Path):
    (root / 'bin').mkdir(parents=True)
    (root / 'lists').mkdir()
    (root / 'bin/winws.exe').write_bytes(b'fake-binary-only-for-tests')
    (root / 'lists/list-general.txt').write_text('example.org')
    (root / 'LICENSE.txt').write_text('MIT')
    bat = ('@echo off\n'
           'start "zapret: %~n0" /min "%BIN%winws.exe" '
           '--wf-tcp=80,443,%GameFilterTCP% --wf-udp=443,%GameFilterUDP% ^\n'
           '--filter-tcp=80,443 --hostlist="%LISTS%list-general.txt" '
           '--dpi-desync=fake\n')
    for name in EXTRA_PROFILE_FILES.values():
        (root / name).write_text(bat, encoding='utf-8')


def test_all_nine_official_extra_modes_are_known_and_not_auto():
    assert len(EXTRA_PROFILE_FILES) == 9
    assert not set(EXTRA_PROFILE_FILES) & set(ALT_MODES)
    assert not set(EXTRA_PROFILE_FILES) & set(ALT_PRIORITY)
    assert set(ALT_PRIORITY) == set(ALT_MODES)
    assert profile_filename('general') == 'general.bat'
    assert profile_filename('fake_tls_auto_alt3') == 'general (FAKE TLS AUTO ALT3).bat'
    with pytest.raises(ValueError):
        profile_filename('../unexpected.bat')


@pytest.mark.parametrize('mode', tuple(EXTRA_PROFILE_FILES))
def test_each_extra_profile_builds_direct_winws_argv(tmp_path, mode):
    synthetic_package(tmp_path)
    spec = build_dpi_spec(tmp_path, mode)
    assert spec.argv[0] == str(tmp_path / 'bin/winws.exe')
    assert '--wf-tcp=80,443' in spec.argv
    assert '--dpi-desync=fake' in spec.argv
    assert not any(item.endswith('.bat') for item in spec.argv)


def test_extra_profile_round_trip_settings(tmp_path):
    for mode in EXTRA_PROFILE_FILES:
        path = tmp_path / (mode + '.json')
        save_settings(Settings(dpi_mode=mode), path)
        assert load_settings(path).dpi_mode == mode


def test_engine_manifest_detects_tampered_extra_profiles(tmp_path):
    synthetic_package(tmp_path)
    write_engine_manifest(tmp_path, release_sha='c' * 64)
    assert engine_integrity(tmp_path, release_sha='c' * 64) == 'verified'
    (tmp_path / 'general (EXP).bat').write_text('untrusted changes')
    assert engine_integrity(tmp_path, release_sha='c' * 64) == 'tampered'


def test_partial_extra_bundle_is_rejected(tmp_path):
    synthetic_package(tmp_path)
    (tmp_path / 'general (EXP).bat').unlink()
    with pytest.raises(ValueError, match='Неполный комплект'):
        write_engine_manifest(tmp_path, release_sha='c' * 64)
