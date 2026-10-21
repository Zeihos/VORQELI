"""Windows-CI-safe smoke: bounded HOSTS inspection on synthetic temp files only."""
from pathlib import Path
from tempfile import TemporaryDirectory
from vorqeli_connect.geohide_uninstall_guard import inspect_pending
from vorqeli_connect.geohide_hosts_feed import readonly_status


def main() -> None:
    with TemporaryDirectory(prefix='vorqeli-rc40-hosts-') as folder:
        root = Path(folder)
        hosts, journal = root / 'hosts', root / 'geo-journal.json'
        hosts.write_bytes(b'127.0.0.1 localhost\r\n')
        assert not inspect_pending(hosts,journal)['pending']
        report = readonly_status(hosts,journal)
        assert report['schema'] == 1 and report['status'] == 'not_installed'
        hosts.write_bytes(hosts.read_bytes()+b'# VORQELI GEOHIDE HOSTS START\r\n')
        assert inspect_pending(hosts,journal)['pending']
        hosts.write_bytes(b'127.0.0.1 localhost\r\n')
        journal.write_text('{"schema":1}',encoding='utf-8')
        assert inspect_pending(hosts,journal)['pending']
    print('GeoHide RC HOSTS preflight smoke passed (temporary files only, no OS changes)')


if __name__=='__main__':
    main()
