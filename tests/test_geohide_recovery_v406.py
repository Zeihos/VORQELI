"""Offline recovery regression tests; only temporary HOSTS copies are written."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

import pytest
from vorqeli_connect import geohide_hosts_feed as feed


SAMPLE = ("### geohide.ru: hosts file\n"
          "# Последнее обновление: 20.10.2026 04:56:02\n"
          "# Регион серверов: RU\n"
          "159.194.200.33 chatgpt.com\n"
          "193.233.112.88 chatgpt.com\n"
          "### geohide.ru: end hosts file\n")
OLD_TELEGRAM = (feed.LEGACY_START + '\n'
                '149.154.167.220 web.telegram.org\n' + feed.LEGACY_END + '\n')


def snapshot():
    return feed.parse_official(SAMPLE,min_domains=1)


def fixtures(tmp_path):
    hosts=tmp_path/'hosts'
    journal=tmp_path/'geo.json'
    hosts.write_text('127.0.0.1 localhost\n' + OLD_TELEGRAM,encoding='utf8')
    return hosts,journal


def journal_payload():
    return {'schema':1,'legacy_block':OLD_TELEGRAM,
            'active_block_sha256':'a'*64,'source_sha256':'b'*64,
            'updated':'2026-10-20'}


def test_normal_apply_and_remove_preserves_legacy_and_manual(tmp_path):
    hosts,journal=fixtures(tmp_path)
    before=hosts.read_bytes()
    result=feed.apply(hosts,snapshot(),journal)
    assert result['official_entries']==2
    assert 'chatgpt.com' in hosts.read_text()
    assert journal.is_file()
    assert feed.remove(hosts,journal) is True
    assert hosts.read_bytes()==before
    assert not journal.exists()


def test_crashed_orphan_journal_can_be_recovered_without_touching_hosts(tmp_path):
    hosts,journal=fixtures(tmp_path)
    # Simulate a crash AFTER writing the journal but BEFORE the HOSTS change:
    # remove legacy first so only unchanged manual entries remain.
    hosts.write_text('127.0.0.1 localhost\n',encoding='utf8')
    journal.write_text(json.dumps(journal_payload()),encoding='utf8')
    before=hosts.read_bytes()
    assert feed.readonly_status(hosts,journal)['status']=='needs_attention'
    assert feed.remove(hosts,journal) is True
    assert not journal.exists()
    assert hosts.read_bytes()==before
    assert feed.readonly_status(hosts,journal)['status']=='not_installed'


def test_orphan_journal_does_not_discard_existing_legacy_block(tmp_path):
    hosts,journal=fixtures(tmp_path)
    journal.write_text(json.dumps(journal_payload()),encoding='utf8')
    before=hosts.read_bytes()
    with pytest.raises(ValueError,match='старый HOSTS'):
        feed.remove(hosts,journal)
    assert journal.exists() and hosts.read_bytes()==before


def test_tampered_orphan_journal_is_never_silently_deleted(tmp_path):
    hosts,journal=fixtures(tmp_path)
    hosts.write_text('127.0.0.1 localhost\n',encoding='utf8')
    d=journal_payload();d['active_block_sha256']='INVALID'
    journal.write_text(json.dumps(d),encoding='utf8')
    with pytest.raises(ValueError,match='целостность'):
        feed.remove(hosts,journal)
    assert journal.exists()


def test_conflicting_manual_telegram_entry_blocks_restore(tmp_path):
    hosts,journal=fixtures(tmp_path)
    feed.apply(hosts,snapshot(),journal)
    original=hosts.read_text()
    # A user adds a manual override after GeoHide was enabled. Do not append
    # the old Telegram mapping on top of their change during rollback.
    hosts.write_text(original+'1.1.1.1 web.telegram.org\n',encoding='utf8')
    current=hosts.read_bytes()
    with pytest.raises(ValueError,match='пересекаются'):
        feed.remove(hosts,journal)
    assert hosts.read_bytes()==current and journal.exists()


def test_manually_edited_geohide_block_blocks_restore(tmp_path):
    hosts,journal=fixtures(tmp_path)
    feed.apply(hosts,snapshot(),journal)
    original=hosts.read_text()
    hosts.write_text(original.replace('159.194.200.33 chatgpt.com','1.1.1.1 chatgpt.com'),encoding='utf8')
    before=hosts.read_bytes()
    with pytest.raises(ValueError,match='edited outside'):
        feed.remove(hosts,journal)
    assert hosts.read_bytes()==before and journal.exists()


def test_recovery_never_uses_real_windows_hosts(tmp_path):
    hosts,journal=fixtures(tmp_path)
    assert hosts.parent==tmp_path
    assert feed.readonly_status(hosts,journal)['geohide_installed'] is False
