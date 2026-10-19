"""v0.28: keyboard, compact geometry and optional Windows chrome regression suite."""
from unittest.mock import patch
import pytest
from vorqeli_connect.ui_navigation import cycle_focus, reveal_target
from vorqeli_connect.window_state import safe_geometry, minimum_window_size
from vorqeli_connect.windows_chrome import dwm_attributes, current_windows_build, apply_windows_chrome


@pytest.mark.parametrize('count, current, back, expected', [
    (0, None, False, None), (0, 0, True, None),
    (1, None, False, 0), (1, 0, True, 0),
    (5, None, False, 0), (5, None, True, 4),
    (5, 0, False, 1), (5, 4, False, 0),
    (5, 2, True, 1), (5, 0, True, 4),
    (5, 42, False, 0), (5, -2, True, 4),
])
def test_cycle_keyboard_focus(count,current,back,expected):
    assert cycle_focus(current,count,backward=back)==expected


@pytest.mark.parametrize('bounds, viewport, content, scroll, result', [
    ((20,20,90,65), (800,500), (1060,710), (0,0), (0,0)),
    ((310,400,450,450), (800,500), (1060,710), (0,0), (0,0)),
    ((850,500,970,550), (800,500), (1060,710), (0,0), (185,65)),
    ((30,25,170,70), (800,500), (1060,710), (210,140), (15,10)),
    ((1030,690,1050,705), (800,500), (1060,710), (0,0), (260,210)),
    ((200,200,400,280), (1200,800), (1060,710), (0,0), (0,0)),
    ((10,10,200,200), (0,700), (1060,710), (20,0), (20,0)),
])
def test_focus_auto_reveal(bounds,viewport,content,scroll,result):
    assert reveal_target(bounds,viewport,content,scroll)==result


def test_compact_geometry_does_not_exceed_screen():
    for w,h in ((960,600),(900,600),(800,550),(640,500)):
        minw,minh=minimum_window_size(w,h)
        assert minw <= w and minh <= h
        size=safe_geometry('1280x900+4500+7000',w,h)
        import re
        values=[int(x) for x in re.findall(r'\d+',size)]
        assert minw<=values[0]<=w
        assert minh<=values[1]<=h
        assert values[2]<=w-values[0]
        assert values[3]<=h-values[1]
        assert 'x' in safe_geometry('nope',w,h)


def test_normal_monitor_keeps_full_content_geometry():
    assert minimum_window_size(1920,1080)==(1060,710)
    assert safe_geometry('1180x760+40+40',1920,1080)=='1180x760+40+40'


@pytest.mark.parametrize('win,build,attributes', [
    (False,22621,()), (True,0,()), (True,17762,()),
    (True,19045,((20,1),)),
    (True,22000,((20,1),(33,2),(38,2))),
    (True,26100,((20,1),(33,2),(38,2))),
])
def test_dwm_version_gating(win,build,attributes):
    assert dwm_attributes(win,build)==attributes


def test_chrome_noop_outside_windows():
    with patch('vorqeli_connect.windows_chrome.os.name','posix'):
        assert current_windows_build()==0
        assert apply_windows_chrome(object())==()


def test_settings_minimum_dns_controls_no_footer_overlap():
    from pathlib import Path
    code=(Path(__file__).resolve().parents[1] / 'src/vorqeli_connect/app.py').read_text(encoding='utf-8')
    assert "self._place_button(x+31+j*151,640,label," in code
    assert "self._text(x+31,h-60,'Изменение модулей" not in code
