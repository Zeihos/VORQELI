"""Offline GUI smoke test. Run via xvfb-run on Linux or in a desktop session."""
from unittest.mock import patch
from vorqeli_connect.config import Settings
from vorqeli_connect.app import ConnectApp

with patch('vorqeli_connect.app.load_settings', return_value=Settings(first_launch_notice=False,launch_at_startup=False,window_geometry='1200x760')):
    with patch.object(ConnectApp,'_launch_tray',lambda self:None):
        app=ConnectApp()
        app.update()
        for page in ('Главная','Диагностика','История','Настройки','О проекте'):
            app._page(page)
            app.update()
            print('OK',page)
        app._quitting=True
        app.destroy()
