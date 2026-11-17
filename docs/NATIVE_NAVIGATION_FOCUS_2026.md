# VORQELI · six-page navigation and focus stability

Native Tk Canvas navigation now exposes all six sections, including
**Сеть и стратегии**. Sidebar icons are drawn with Canvas lines/ovals and
have the same hit target as their navigation row; they are not screenshots
or Unicode glyphs that depend on the installed Windows font.

Keyboard activation reconciles focus after an action. A new control at the
same list index is not automatically treated as the old target. Missing or
ambiguous labels clear the ring; a unique surviving label can retain it.
A page callback that clears focus explicitly remains authoritative.

Pointer clicks still clear the keyboard-only focus ring and allow repeated
activation without selecting another button.

## Acceptance tests

- Run all pytest tests and the Windows CI installer smoke
- Tab/Shift+Tab through all six sidebar rows and activate with Enter/Space
- Trigger a diagnostic action via keyboard while it becomes disabled
- Retry the same mouse button twice; no stuck white focus ring
- Check compact windows and Windows DPI 100%, 125%, 150% and 200%

The bypass core, DNS, HOSTS, autostart and system networking are unchanged.
