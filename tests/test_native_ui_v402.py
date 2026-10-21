"""RC 0.40.2: native row accessibility, diagnostic busy state and bounded icons."""
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from PIL import Image

from vorqeli_connect import native_ui as ui
from test_native_ui_v401 import FakeApp


@pytest.fixture(autouse=True)
def _mock_icons(monkeypatch):
    monkeypatch.setattr(ui.Scene,'logo',lambda *args: True)
    monkeypatch.setattr(ui.Scene,'brand_icon',lambda *args: True)


def test_busy_diagnostics_are_disabled_and_cannot_enqueue_jobs():
    app=FakeApp()
    app.selected_page='Диагностика'
    app.running_job=True
    app.detail='Проверяем сервис: YouTube'
    ui.draw(app)
    labels=[label for _,_,label in app._controls]
    assert 'ПРОВЕРИТЬ ВСЁ' not in labels
    assert 'ПРОВЕРИТЬ' not in labels
    assert 'ВЫПОЛНЯЕТСЯ…' not in labels
    assert 'DNS / HOSTS' in labels   # read-only inspection still available
    assert not app.actions


def test_idle_diagnostics_reenable_each_service():
    app=FakeApp();app.selected_page='Диагностика';app.running_job=False
    ui.draw(app)
    labels=[label for _,_,label in app._controls]
    assert labels.count('ПРОВЕРИТЬ')==5
    assert labels.count('ПРОВЕРИТЬ ВСЁ')==1


def test_history_rows_are_clickable_and_show_full_message(monkeypatch):
    long='Событие ' + 'длинное_описание_'*25
    entry={'timestamp':'2026-10-22T06:07:08+07:00','action':'connection','message':long}
    monkeypatch.setattr(ui,'recent_events',lambda limit=100:[entry])
    monkeypatch.setattr(ui,'load_history',lambda:[])
    messages=[]
    monkeypatch.setattr(ui.messagebox,'showinfo',lambda title,text,**kw:messages.append((title,text)))
    app=FakeApp();app.selected_page='История'
    ui.draw(app)
    assert ('history_row_0','<Button-1>') in app.canvas.tags
    ix=[i for i,(_,_,label) in enumerate(app._controls) if label.startswith('Событие:')]
    assert len(ix)==1
    # One shared callback supports both keyboard activation and real mouse tags.
    app.canvas.tags[('history_row_0','<Button-1>')](NS())
    assert len(messages)==1
    assert long in messages[0][1]
    assert 'connection' in messages[0][1]
    assert '06:07:08' in messages[0][1]


def test_history_uses_current_page_and_does_not_open_another_entry(monkeypatch):
    entries=[{'timestamp':str(i),'action':'state','message':f'row{i}'} for i in range(21)]
    monkeypatch.setattr(ui,'recent_events',lambda limit=100:entries)
    monkeypatch.setattr(ui,'load_history',lambda:[])
    shown=[]
    monkeypatch.setattr(ui.messagebox,'showinfo',lambda title,text,**kw:shown.append(text))
    app=FakeApp();app.selected_page='История';app._native_history_page=1
    ui.draw(app)
    app.canvas.tags[('history_row_0','<Button-1>')](NS())
    assert 'row10' in shown[-1]
    assert 'row0' not in shown[-1]


def test_repeated_icon_resampling_uses_bounded_cache(tmp_path,monkeypatch):
    from PIL import Image as PILImage
    icon=tmp_path/'icon.png'
    PILImage.new('RGBA',(64,64),(10,40,200,255)).save(icon)
    original=PILImage.open
    opened=[]
    def spy(*a,**kw):
        opened.append(a[0]);return original(*a,**kw)
    ui._scaled_icon.cache_clear()
    monkeypatch.setattr(ui.Image,'open',spy)
    first=ui._scaled_icon(icon,32)
    second=ui._scaled_icon(icon,32)
    third=ui._scaled_icon(icon,20)
    assert first is second and first.size==(32,32)
    assert third.size==(20,20) and third is not first
    assert opened==[icon,icon]
    assert ui._scaled_icon.cache_info().maxsize<=128
    ui._scaled_icon.cache_clear()


def test_real_draw_does_not_load_whole_screen_image():
    source=Path(ui.__file__).read_text(encoding='utf8')
    assert 'artwork(page)' not in source
    assert 'ui_assets/premium/home.png' not in source
    assert 'create_polygon' in source and 'create_text' in source
