"""Real Tk widget interaction test (offline, no network changes). Needs display."""
from unittest.mock import patch
from vorqeli_connect.config import Settings
from vorqeli_connect.app import ConnectApp

with patch('vorqeli_connect.app.load_settings', return_value=Settings(
        first_launch_notice=False, launch_at_startup=False, desired_enabled=False)):
    with patch.object(ConnectApp,'_launch_tray',lambda self:None), \
         patch('vorqeli_connect.window_state.minimum_window_size', return_value=(700, 480)):
        app=ConnectApp()
        try:
            app.geometry('830x570+0+0')
            app.update()
            app._draw()
            app.update()
            assert app._scrollbars_visible==(True,True),app._scrollbars_visible
            assert app._controls
            class E: state=0
            for i in range(len(app._controls)):
                app._keyboard_tab(E())
                assert app._focused_control_index==i
            assert app._focused_control_index==len(app._controls)-1
            app._keyboard_tab(E())
            assert app._focused_control_index==0
            app._keyboard_shift_tab(E())
            assert app._focused_control_index==len(app._controls)-1
            app._focus_control(0)
            app._keyboard_activate(E())
            assert app.selected_page=='Главная'
            app._page('Настройки')
            app.update()
            assert app.selected_page=='Настройки'
            assert any(label=='IPv4 DNS' for _,_,label in app._controls)
            assert any(label=='DoH · HTTPS' for _,_,label in app._controls)
            app._focus_control(len(app._controls)-1)
            assert app.canvas.canvasy(0) > 0, app.canvas.canvasy(0)
            app.geometry('1220x790+0+0')
            app.update()
            app._draw()
            app.update()
            assert app._scrollbars_visible==(False,False),app._scrollbars_visible
            print('Keyboard, focus ring and compact scroll: OK')
        finally:
            app._quitting=True
            app.destroy()
