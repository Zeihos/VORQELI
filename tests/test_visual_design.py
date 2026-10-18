from vorqeli_connect.visual_design import scene,layout,tint_status,fit_line
from vorqeli_connect.window_state import safe_geometry


def test_scene_dimensions_and_cache():
    first=scene(1140,740,'Главная')
    second=scene(1140,740,'Главная')
    assert first.size == (1140,740)
    assert first is second
    assert first.mode == 'RGBA'


def test_layout_resizes():
    small=layout(1060,710)
    large=layout(1400,880)
    assert large['content_width'] > small['content_width']
    assert large['footer_top'] == small['footer_top']
    assert large['bottom'] > small['bottom']


def test_status_palette_and_ellipsize():
    assert tint_status('error') != tint_status('connected')
    assert fit_line('  Some \n message ',count=30) == 'Some message'
    assert len(fit_line('a'*60,count=14)) == 14


def test_recover_offscreen_geometry():
    assert safe_geometry('1170x740+9000-200',1920,1080) == '1170x740+750+0'
    assert safe_geometry('bad text',1920,1080) == '1170x740'
    assert safe_geometry('1170x740',1920,1080) == '1170x740'
    assert safe_geometry('1600x1200',1366,768) == '1366x768'
