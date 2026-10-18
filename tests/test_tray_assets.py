from PIL import Image
from vorqeli_connect.tray_assets import tray_icon, STATUS_COLORS


def test_tray_status_colors_and_no_mutation():
    logo=Image.new('RGBA',(128,128),(180,80,250,255))
    backup=logo.copy()
    off=tray_icon(logo,'off')
    on=tray_icon(logo,'connected')
    assert on.size==(64,64)
    assert off.mode=='RGBA'
    assert off.getpixel((51,51)) != on.getpixel((51,51))
    assert logo.tobytes()==backup.tobytes()
    assert set(STATUS_COLORS)=={'connected','partial','error','off'}
