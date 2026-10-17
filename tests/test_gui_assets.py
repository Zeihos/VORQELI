from pathlib import Path
from vorqeli_connect.app import asset, gradient_background

def test_assets_exist():
    assert asset('VORQELI-logo.png').is_file()
    assert asset('VORQELI.ico').is_file()

def test_gradient_renders():
    im=gradient_background(600,520)
    assert im.size==(600,520)
    assert im.mode=='RGBA'
