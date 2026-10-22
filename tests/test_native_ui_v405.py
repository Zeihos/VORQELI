"""RC405: diagnostic freshness never depends on mutable progress copy.

Offline tests, no Windows networking, DNS or HOSTS changes.
"""
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
from vorqeli_connect import native_ui as ui
from test_native_ui_v401 import FakeApp


@pytest.fixture(autouse=True)
def _icons(monkeypatch):
    monkeypatch.setattr(ui.Scene,'logo',lambda *args: True)
    monkeypatch.setattr(ui.Scene,'brand_icon',lambda *args: True)


def capture(monkeypatch):
    got=[]; original=ui.Scene.txt
    def observe(self,x,y,label,*args,**kwargs):
        got.append(str(label))
        return original(self,x,y,label,*args,**kwargs)
    monkeypatch.setattr(ui.Scene,'txt',observe)
    return got


def scan_app():
    a=FakeApp()
    a.selected_page='Диагностика'
    a.last_results=[(k,'Доступен') for k in ui.SERVICE_NAMES]
    a._diagnostic_scope=None
    a._diagnostic_fresh=set()
    return a


def test_saved_result_is_not_shown_as_live_green(monkeypatch):
    messages=capture(monkeypatch)
    app=scan_app();ui.draw(app)
    assert messages.count('Ранее: HTTPS OK')==5
    assert 'HTTPS OK' not in messages


def test_current_session_completed_results_are_live(monkeypatch):
    messages=capture(monkeypatch)
    app=scan_app();app._diagnostic_fresh.update(ui.SERVICE_NAMES)
    ui.draw(app)
    assert messages.count('HTTPS OK')==5
    assert 'Ранее: HTTPS OK' not in messages


def test_single_rescan_is_stable_after_unrelated_progress(monkeypatch):
    messages=capture(monkeypatch)
    app=scan_app();app._diagnostic_fresh.update(ui.SERVICE_NAMES)
    app.running_job=True;app._diagnostic_scope='YouTube'
    app.detail='Другое сообщение от модуля во время проверки'
    ui.draw(app)
    assert messages.count('Проверяется…')==1
    assert messages.count('HTTPS OK')==4
    assert 'Проверяем: YouTube' in messages


def test_full_rescan_displays_no_stale_success(monkeypatch):
    messages=capture(monkeypatch)
    app=scan_app();app.running_job=True;app._diagnostic_scope='all'
    app.detail='WinWS: другое сообщение'
    ui.draw(app)
    assert messages.count('Проверяется…')==5
    assert 'HTTPS OK' not in messages
    assert 'Проверяем все сервисы…' in messages


def test_unrelated_job_never_reads_diagnostic_word_from_copy(monkeypatch):
    messages=capture(monkeypatch)
    app=scan_app();app.running_job=True
    app._diagnostic_scope=None
    app.detail='Проверяем сервис: YouTube'  # stale text from older operation
    ui.draw(app)
    assert 'Проверяется…' not in messages
    assert messages.count('Ранее: HTTPS OK')==5


def test_fresh_failure_never_turns_green():
    label,color=ui.diagnostic_result('ChatGPT','HTTP 403',{'ChatGPT'})
    assert '403' in label and color!=ui.C['green']
    label,color=ui.diagnostic_result('ChatGPT','HTTP 429',set())
    assert label.startswith('Ранее:') and color==ui.C['dim']


def test_unchecked_remains_neutral():
    label,color=ui.diagnostic_result('ChatGPT','Не проверено',set())
    assert label=='Не проверено' and color==ui.C['dim']


def test_only_five_services():
    assert len(ui.SERVICE_NAMES)==5
    assert 'Microsoft (Copilot, Designer, Xbox)' in ui.SERVICE_NAMES


def test_render_never_calls_network(monkeypatch):
    app=scan_app()
    for page in ui.PAGES:
        app.selected_page=page
        ui.draw(app)
    assert app.actions==[]
