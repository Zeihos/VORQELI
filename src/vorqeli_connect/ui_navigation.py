"""Pure keyboard navigation helpers for canvas-backed desktop controls."""
from __future__ import annotations


def cycle_focus(current: int | None, count: int, *, backward: bool = False) -> int | None:
    """Cycle only through enabled controls. None means no previous focus."""
    if count <= 0:
        return None
    if current is None or not 0 <= current < count:
        return count - 1 if backward else 0
    return (current + (-1 if backward else 1)) % count


def reveal_target(bounds: tuple[int, int, int, int],
                  viewport: tuple[int, int], content: tuple[int, int],
                  scroll: tuple[int, int], margin: int = 15) -> tuple[int, int]:
    """Return scroll offsets keeping the target control visible when compact."""
    x1, y1, x2, y2 = bounds
    vw, vh = viewport
    cw, ch = content
    ox, oy = scroll
    if vw <= 0 or vh <= 0:
        return ox, oy
    if x1 < ox + margin:
        ox = x1 - margin
    elif x2 > ox + vw - margin:
        ox = x2 - vw + margin
    if y1 < oy + margin:
        oy = y1 - margin
    elif y2 > oy + vh - margin:
        oy = y2 - vh + margin
    return (max(0, min(ox, max(0, cw-vw))),
            max(0, min(oy, max(0, ch-vh))))
