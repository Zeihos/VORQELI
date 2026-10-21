"""Uninstall safety must reject managed HOSTS before removing the cleanup UI."""
from pathlib import Path
import pytest
from vorqeli_connect.geohide_uninstall_guard import inspect_pending
from vorqeli_connect import geohide_hosts_feed as feed


def files(tmp_path: Path, data: bytes=b'127.0.0.1 localhost\r\n'):
    hosts=tmp_path/'hosts'
    hosts.write_bytes(data)
    return hosts,tmp_path/'geohide-hosts-restore.json'


def test_clean_system_hosts_allows_cleanup(tmp_path):
    hosts,journal=files(tmp_path)
    assert inspect_pending(hosts,journal)=={'pending':False,'geohide_block':False,
        'optional_block':False,'journal_present':False}


@pytest.mark.parametrize('marker',(
    b'# VORQELI GEOHIDE HOSTS START',b'# VORQELI GEOHIDE HOSTS END',
    b'# VORQELI OPTIONAL HOSTS START',b'# VORQELI OPTIONAL HOSTS END'))
def test_each_managed_marker_blocks_uninstall_even_if_pair_malformed(tmp_path,marker):
    hosts,journal=files(tmp_path,b'127.0.0.1 localhost\n'+marker+b'\n')
    assert inspect_pending(hosts,journal)['pending']


def test_orphaned_recovery_journal_blocks_removal(tmp_path):
    hosts,journal=files(tmp_path)
    journal.write_text('{"schema":1}',encoding='utf8')
    assert inspect_pending(hosts,journal)['pending']


def test_unknown_or_unreadable_state_fails_closed(tmp_path):
    hosts,journal=files(tmp_path)
    hosts.unlink()
    with pytest.raises(FileNotFoundError):inspect_pending(hosts,journal)
    hosts,journal=files(tmp_path,b'x'*(2*1024*1024+1))
    with pytest.raises(ValueError):inspect_pending(hosts,journal)


def test_linked_hosts_and_journal_rejected(tmp_path):
    hosts,journal=files(tmp_path)
    linked=tmp_path/'other-hosts';linked.symlink_to(hosts)
    with pytest.raises(ValueError):inspect_pending(linked,journal)
    journal.symlink_to(hosts)
    with pytest.raises(ValueError):inspect_pending(hosts,journal)


def test_readonly_status_is_honest_and_redacted(tmp_path):
    hosts,journal=files(tmp_path,b'127.0.0.1 localhost\n# confidential user comment\n')
    status=feed.readonly_status(hosts,journal)
    assert status['status']=='not_installed'
    assert status['managed_domains']==0
    assert 'confidential' not in str(status)
    journal.write_text('{"schema":1,"legacy_block":"","active_block_sha256":"fake"}',encoding='utf8')
    assert feed.readonly_status(hosts,journal)['status']=='needs_attention'


def test_readonly_status_verified_after_apply(tmp_path):
    hosts,journal=files(tmp_path)
    rows=['### geohide.ru: hosts file','# Последнее обновление: 21.10.2026 00:00:00',
          '# Регион серверов: RU']
    rows.extend(f'159.194.200.33 test{i}.example.com' for i in range(205))
    rows.extend(['159.194.200.33 claude.ai','193.233.112.67 claude.ai',
                 '### geohide.ru: end hosts file'])
    snapshot=feed.parse_official('\n'.join(rows)+'\n')
    feed.apply(hosts,snapshot,journal,'149.154.167.220 web.telegram.org\n')
    report=feed.readonly_status(hosts,journal)
    assert report['status']=='installed_verified'
    assert report['managed_ip_entries'] >= 207
    assert report['journal_verified'] is True
    assert feed.remove(hosts,journal)
    assert feed.readonly_status(hosts,journal)['status']=='not_installed'


def test_preflight_rejects_hosts_before_touching_startup(tmp_path):
    from vorqeli_connect.uninstall_safety import cleanup_for_uninstall
    hosts,journal=files(tmp_path,b'# VORQELI GEOHIDE HOSTS START\n')
    called=[]
    result=cleanup_for_uninstall(
        check_running=lambda:False,
        pending_hosts=lambda:inspect_pending(hosts,journal)['pending'],
        disable_startup=lambda v:called.append(v) or 'disabled',
        audit_startup=lambda:'unsupported',
        backup=tmp_path/'dns.json')
    assert not result.success
    assert not called
    assert 'HOSTS' in result.details[0]


def test_preflight_failed_inspection_blocks_cleanup(tmp_path):
    from vorqeli_connect.uninstall_safety import cleanup_for_uninstall
    hosts,journal=files(tmp_path)
    hosts.unlink()
    result=cleanup_for_uninstall(check_running=lambda:False,
       pending_hosts=lambda:inspect_pending(hosts,journal)['pending'],
       disable_startup=lambda _:(_ for _ in ()).throw(AssertionError('must not run')),
       backup=tmp_path/'dns.json')
    assert not result.success
    assert 'HOSTS' in result.details[0]


def test_source_cli_does_not_require_gui_or_network():
    root=Path(__file__).resolve().parents[1]
    app=(root/'src/vorqeli_connect/app.py').read_text(encoding='utf8')
    assert "parser.add_argument('--geohide-hosts-status'" in app
    assert app.index('    if args.geohide_hosts_status:') < app.index('    if args.self_test:')
    assert 'readonly_status(hosts_path(), APP_DIR/' in app
