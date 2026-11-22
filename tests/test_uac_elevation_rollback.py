"""Fail-safe ON/OFF persistence across Windows UAC elevation."""
from types import SimpleNamespace as NS

import pytest
from vorqeli_connect import app as application
from vorqeli_connect.config import Settings


def fake_ui():
    calls = []
    settings = Settings(desired_enabled=False, connect_dpi=True,
                        connect_telegram=False, connect_dns=False)
    ui = NS(
        settings=settings,
        _quitting=False,
        running_job=False,
        _disconnecting=False,
        detail='',
        _draw=lambda: calls.append('draw'),
        _quit_now=lambda **kwargs: calls.append(('quit', kwargs)),
    )
    return ui, calls


@pytest.fixture
def windows_unprivileged(monkeypatch):
    monkeypatch.setattr(application, 'os', NS(name='nt'))
    monkeypatch.setattr(application, 'is_admin', lambda: False)
    return monkeypatch


def test_unwritable_settings_do_not_launch_uac(windows_unprivileged):
    ui, calls = fake_ui()
    def fail(settings):
        raise OSError('disk unavailable')
    windows_unprivileged.setattr(application, 'save_settings', fail)
    windows_unprivileged.setattr(application, 'relaunch_elevated',
                               lambda: pytest.fail('must not elevate with unsaved ON intent'))
    application.ConnectApp._start_connect(ui)
    assert ui.settings.desired_enabled is False
    assert 'перед UAC' in ui.detail
    assert calls == ['draw']


def test_uac_declined_restores_previous_off_intent(windows_unprivileged):
    ui, calls = fake_ui()
    writes = []
    windows_unprivileged.setattr(application, 'save_settings',
                               lambda settings: writes.append(settings.desired_enabled))
    windows_unprivileged.setattr(application, 'relaunch_elevated', lambda: False)
    windows_unprivileged.setattr(application.messagebox, 'showwarning',
                               lambda *args, **kwargs: calls.append('warning'))
    application.ConnectApp._start_connect(ui)
    assert writes == [True, False]
    assert ui.settings.desired_enabled is False
    assert calls == ['warning', 'draw']


def test_uac_failure_and_failed_rollback_warns_instead_of_crashing(windows_unprivileged):
    ui, calls = fake_ui()
    writes = []
    def write(settings):
        writes.append(settings.desired_enabled)
        if len(writes) == 2:
            raise OSError('rollback denied')
    windows_unprivileged.setattr(application, 'save_settings', write)
    windows_unprivileged.setattr(application, 'relaunch_elevated',
                               lambda: (_ for _ in ()).throw(OSError('UAC unavailable')))
    windows_unprivileged.setattr(application.messagebox, 'showwarning',
                               lambda *args, **kwargs: calls.append('warning'))
    application.ConnectApp._start_connect(ui)
    assert writes == [True, False]
    assert ui.settings.desired_enabled is False
    assert 'автозапуск' in ui.detail.lower()
    assert calls == ['draw', 'warning']


def test_successful_uac_launch_quits_old_instance(windows_unprivileged):
    ui, calls = fake_ui()
    writes = []
    windows_unprivileged.setattr(application, 'save_settings',
                               lambda settings: writes.append(settings.desired_enabled))
    windows_unprivileged.setattr(application, 'relaunch_elevated', lambda: True)
    application.ConnectApp._start_connect(ui)
    assert writes == [True]
    assert calls == [('quit', {'skip_disconnect': True})]
