from vorqeli_connect.app import asset
from vorqeli_connect.visual_design import scene


def test_assets_exist():
    assert asset('VORQELI-logo.png').is_file()
    assert asset('VORQELI.ico').is_file()


def test_gradient_renders():
    image=scene(1060,710,'Главная')
    assert image.size==(1060,710)
    assert image.mode=='RGBA'
