"""Optional Windows DWM titlebar treatment. Never required for connecting.

Mica on Windows 11 is requested for the top-level backdrop, but the Pillow
client scene remains opaque. This must not be advertised as a fully translucent
native client area. Silently tolerate older Windows or disabled composition.
"""
from __future__ import annotations
import os


def dwm_attributes(is_windows: bool, build: int) -> tuple[tuple[int, int], ...]:
    """Numeric DWM attributes with correct platform feature gates."""
    if not is_windows or build < 17763:
        return ()
    attributes = [(20, 1)]  # DWMWA_USE_IMMERSIVE_DARK_MODE
    if build >= 22000:
        attributes.extend(((33, 2), (38, 2)))  # rounded corners, Mica main window
    return tuple(attributes)


def current_windows_build() -> int:
    if os.name != 'nt':
        return 0
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r'SOFTWARE\Microsoft\Windows NT\CurrentVersion') as key:
            return int(winreg.QueryValueEx(key, 'CurrentBuildNumber')[0])
    except (OSError, ValueError, TypeError):
        return 0


def apply_windows_chrome(tk_window) -> tuple[int, ...]:
    """Best-effort DWM settings for the real toplevel HWND (never UAC/elevation)."""
    if os.name != 'nt':
        return ()
    import ctypes
    try:
        build = current_windows_build()
        tk_window.update_idletasks()
        child_hwnd = tk_window.winfo_id()
        hwnd = ctypes.windll.user32.GetParent(child_hwnd) or child_hwnd
        done = []
        for attribute, value in dwm_attributes(True, build):
            data = ctypes.c_int(value)
            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(data), ctypes.sizeof(data))
            if result == 0:
                done.append(attribute)
        return tuple(done)
    except (OSError, ValueError, AttributeError):
        return ()
