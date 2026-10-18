from vorqeli_connect.app import asset
from vorqeli_connect.visual_design import scene


def test_assets_exist():
    assert asset('VORQELI-logo.png').is_file()
    assert asset('VORQELI.ico').is_file()


def test_asset_resolves_checkout_after_package_install(tmp_path, monkeypatch):
    from vorqeli_connect import app
    assets = tmp_path / 'assets'
    assets.mkdir()
    (assets / 'logo.png').write_bytes(b'test-image')
    fake_site_file = tmp_path / 'installed' / 'site-packages' / 'vorqeli_connect' / 'app.py'
    monkeypatch.setattr(app, '__file__', str(fake_site_file))
    monkeypatch.delattr(app.sys, '_MEIPASS', raising=False)
    monkeypatch.chdir(tmp_path)
    assert app.asset('logo.png') == assets / 'logo.png'


def test_gradient_renders():
    image=scene(1060,710,'Главная')
    assert image.size==(1060,710)
    assert image.mode=='RGBA'
