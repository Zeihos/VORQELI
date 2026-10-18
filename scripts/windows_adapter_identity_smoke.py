"""Read-only Windows CI: ensure DNS snapshots contain stable adapter GUIDs.

No DNS/registry/driver changes are made. GitHub hosted runners may have no
active physical NICs in the exact adapter class managed by VORQELI; in that
case the capability smoke skips while offline regression tests remain active.
"""
import os
from vorqeli_connect.geohide import query_dns_state


def main() -> int:
    if os.name != 'nt':
        print('Windows-only adapter smoke skipped')
        return 0
    adapters = query_dns_state()
    for entry in adapters:
        if not entry.get('guid'):
            raise RuntimeError('Get-NetAdapter snapshot lacks InterfaceGuid')
    print('VORQELI: adapter snapshot identity checked for', len(adapters), 'adapters')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
