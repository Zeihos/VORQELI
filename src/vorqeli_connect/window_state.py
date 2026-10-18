"""Validate previously saved window bounds when monitor configuration changes."""
from __future__ import annotations
import re

_PATTERN = re.compile(r"^(\d{3,4})x(\d{3,4})(?:([+-]\d+)([+-]\d+))?$")


def minimum_window_size(screen_width: int, screen_height: int) -> tuple[int, int]:
    """On a small/DPI-scaled desktop, show a scrollable rather than clipped UI."""
    return (min(screen_width, 1060, max(600, screen_width - 64)),
            min(screen_height, 710, max(440, screen_height - 90)))


def safe_geometry(saved: str, screen_width: int, screen_height: int) -> str:
    compact_w, compact_h = minimum_window_size(screen_width, screen_height)
    min_w = 1060 if screen_width >= 1060 else compact_w
    min_h = 710 if screen_height >= 710 else compact_h
    max_w = max(min_w, screen_width if screen_width >= 1060 else screen_width - 20)
    max_h = max(min_h, screen_height if screen_height >= 710 else screen_height - 30)
    match = _PATTERN.fullmatch(saved or '')
    if not match:
        return f"{max(min_w, min(1170, max_w))}x{max(min_h, min(740, max_h))}"
    width,height = int(match[1]),int(match[2])
    width = max(min_w,min(width,max_w))
    height = max(min_h,min(height,max_h))
    if match[3] is None:
        return f'{width}x{height}'
    x,y=int(match[3]),int(match[4])
    # Do not allow stale coordinates to strand the window off-screen.
    x=max(0,min(x,max(0,screen_width-width)))
    y=max(0,min(y,max(0,screen_height-height)))
    return f'{width}x{height}+{x}+{y}'
