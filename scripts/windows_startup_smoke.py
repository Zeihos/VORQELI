"""Windows-only end-to-end smoke test of per-user startup registry fallback.

Safe for a disposable GitHub Actions runner. Does not start DPI/proxy, create an
admin task or change DNS. Refuses to edit an existing VORQELI registration.
"""
from __future__ import annotations

import os
import sys


def main() -> int:
    if os.name != 'nt':
        print('Windows-only test: skipped')
        return 0
    from vorqeli_connect import startup
    if startup.registration_status() != 'missing':
        print('Refusing to touch a preexisting or unverified startup registration')
        return 2
    created = False
    try:
        result = startup.configure_startup(True, elevated=False)
        created = result == 'registry'
        if not created or startup.registration_status() != 'registry':
            raise AssertionError('HKCU Run registration was not verified after creation')
        print('HKCU Run registration successfully created and verified')
    finally:
        if created:
            # Cleanup is permitted only if our exact command is still present.
            startup.configure_startup(False, elevated=False)
    if startup.registration_status() != 'missing':
        raise AssertionError('Autostart was not fully removed')
    print('HKCU Run registration successfully removed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
