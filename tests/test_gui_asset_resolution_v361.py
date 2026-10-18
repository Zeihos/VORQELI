"""Regression for asset lookup when pip installs project on Windows."""
from pathlib import Path
import sys
import pytest
from vorqeli_connect import app


def test_source_checkout_logo_and_icon_are_resolved():
    for item in ('VORQELI-logo.png', 'VORQELI.ico', 'VORQELI-hosts-optional.txt'):
        assert app.asset(item).is_file()


def test_installed_package_prefers_bundled_resources(tmp_path, monkeypatch):
    package = tmp_path / 'python' / 'Lib' / 'site-packages' / 'vorqeli_connect'
    resources = package / 'ui_assets'
    resources.mkdir(parents=True)
    (resources / 'logo.png').write_bytes(b'packaged-logo')
    other = tmp_path / 'assets'
    other.mkdir()
    (other / 'logo.png').write_bytes(b'other-logo')
    monkeypatch.setattr(app, '__file__', str(package / 'app.py'))
    monkeypatch.delattr(app.sys, '_MEIPASS', raising=False)
    monkeypatch.chdir(tmp_path)
    assert app.asset('logo.png') == resources / 'logo.png'


def test_installed_package_can_locate_checkout_assets(tmp_path, monkeypatch):
    assets = tmp_path / 'assets'
    assets.mkdir()
    (assets / 'logo.png').write_bytes(b'test')
    fake = tmp_path / 'python' / 'Lib' / 'site-packages' / 'vorqeli_connect' / 'app.py'
    monkeypatch.setattr(app, '__file__', str(fake))
    monkeypatch.delattr(app.sys, '_MEIPASS', raising=False)
    monkeypatch.chdir(tmp_path)
    assert app.asset('logo.png') == assets / 'logo.png'


def test_frozen_resource_does_not_fall_back_to_untrusted_cwd(tmp_path, monkeypatch):
    image = tmp_path / 'assets' / 'logo.png'
    image.parent.mkdir()
    image.write_bytes(b'from-cwd')
    frozen = tmp_path / 'bundle'
    (frozen / 'assets').mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(app.sys, '_MEIPASS', str(frozen), raising=False)
    assert app.asset('logo.png') == frozen / 'assets' / 'logo.png'


@pytest.mark.parametrize('name', ['../secret.txt', 'assets/logo.png', '..', '.', '', '/tmp/logo.png', r'foo\bar'])
def test_asset_rejects_unsafe_names(name):
    with pytest.raises(ValueError):
        app.asset(name)


def test_wheel_manifest_includes_gui_resources():
    root = Path(__file__).resolve().parents[1]
    toml = (root / 'pyproject.toml').read_text(encoding='utf-8')
    assert '"ui_assets/*"' in toml
    for name in ('VORQELI-logo.png', 'VORQELI.ico', 'VORQELI-hosts-optional.txt'):
        src = root / 'assets' / name
        packaged = root / 'src' / 'vorqeli_connect' / 'ui_assets' / name
        assert src.is_file() and packaged.is_file()
        assert src.read_bytes() == packaged.read_bytes()
