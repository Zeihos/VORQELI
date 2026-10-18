from vorqeli_connect.ui_copy import main_status,module_caption,connection_disclaimer
from vorqeli_connect.visual_design import button_skin


def test_copy_never_equates_process_started_with_bypass_success():
    assert 'запущены' in main_status('connected',False)
    assert 'Подключаем' in main_status('off',True)
    assert 'Отключаем' in main_status('off',True,True)
    assert 'отдельно' in connection_disclaimer('connected')
    assert 'ТРЕБУЕТ' in module_caption('error',True)
    assert 'ВЫКЛЮЧЕН' in module_caption('on',False)


def test_glossy_button_has_transparent_round_corners():
    base=button_skin(190,58,accent=True)
    hover=button_skin(190,58,accent=True,hover=True)
    disabled=button_skin(190,58,disabled=True)
    assert base.mode=='RGBA'
    assert base.getpixel((0,0))[3]==0
    assert base.getpixel((90,20))!=hover.getpixel((90,20))
    assert disabled.getpixel((90,20))!=base.getpixel((90,20))
