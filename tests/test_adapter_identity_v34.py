"""v0.34: prevent stale interface-index reuse from touching a foreign adapter."""
from __future__ import annotations
import json
import pytest
from vorqeli_connect import geohide

NIC_A = 'd8eadc4d-6417-487e-86bb-e4d3b889c3a1'
NIC_B = '21941a94-f95a-4bd2-b56f-799ba70c8d60'


def adapter(idx=4, *, guid=NIC_A, alias='Ethernet', addresses=('9.9.9.9',), manual='9.9.9.9'):
    return {'index':idx,'guid':guid,'alias':alias,'before':list(addresses),'manual':manual}


def test_guid_accepts_windows_braces_and_normalizes():
    entry = geohide._validate_state([adapter(guid='{'+NIC_A.upper()+'}')])[0]
    assert entry['guid'] == NIC_A
    assert geohide.adapter_matches(entry, adapter(guid=NIC_A, alias='Ethernet renamed'))


@pytest.mark.parametrize('value', ['garbage', '{'+NIC_A, NIC_A+'}', NIC_A+';calc', '', 7, None])
def test_bad_guid_rejected(value):
    with pytest.raises(ValueError, match='идентификатор'):
        geohide._validate_state([adapter(guid=value)])


def test_duplicate_guid_rejected_even_across_indices():
    with pytest.raises(ValueError, match='Повторяющийся GUID'):
        geohide._validate_state([adapter(idx=1),adapter(idx=2)])


def test_restoration_blocks_reused_interface_index(tmp_path, monkeypatch):
    journal=tmp_path/'restore.json'
    geohide._save_state([adapter(addresses=('1.1.1.1',))],journal)
    monkeypatch.setattr(geohide,'query_dns_state',lambda:[adapter(guid=NIC_B,addresses=geohide.GEOHIDE_IPV4)])
    changed=[]
    monkeypatch.setattr(geohide,'_apply_one',lambda *a:changed.append(a))
    with pytest.raises(RuntimeError,match='адаптер изменился'):
        geohide.restore_dns(journal)
    assert changed == []
    assert json.loads(journal.read_text())['interfaces'][0]['guid']==NIC_A


def test_restore_succeeds_with_alias_change_when_guid_same(tmp_path, monkeypatch):
    journal=tmp_path/'restore.json'
    geohide._save_state([adapter(addresses=('1.1.1.1',))],journal)
    effective=list(geohide.GEOHIDE_IPV4)
    def snapshot():
        return [adapter(alias='Renamed network',addresses=effective)]
    def apply(idx, addresses, guid):
        assert guid == NIC_A
        assert idx == 4
        effective[:]=addresses or []
    monkeypatch.setattr(geohide,'query_dns_state',snapshot)
    monkeypatch.setattr(geohide,'_apply_one',apply)
    assert geohide.restore_dns(journal) is True
    assert not journal.exists()
    assert effective == ['9.9.9.9']


def test_old_backup_alias_mismatch_fails_closed(tmp_path, monkeypatch):
    journal=tmp_path/'restore.json'
    prior=adapter(addresses=('1.1.1.1',))
    del prior['guid']
    geohide._save_state([prior],journal)
    monkeypatch.setattr(geohide,'query_dns_state',lambda:[adapter(alias='New network',addresses=geohide.GEOHIDE_IPV4)])
    monkeypatch.setattr(geohide,'_apply_one',lambda *a:pytest.fail('changed wrong adapter'))
    with pytest.raises(RuntimeError,match='адаптер изменился'):
        geohide.restore_dns(journal)
    assert journal.exists()


def test_resume_backup_rejects_reused_index(tmp_path, monkeypatch):
    journal=tmp_path/'restore.json'
    geohide._save_state([adapter(addresses=('1.1.1.1',))],journal)
    monkeypatch.setattr(geohide,'query_dns_state',lambda:[adapter(guid=NIC_B,addresses=geohide.GEOHIDE_IPV4)])
    with pytest.raises(RuntimeError,match='резервная копия'):
        geohide.enable_dns(journal,probe=False)


def test_apply_script_guards_identity_in_same_shell(monkeypatch):
    received=[]
    monkeypatch.setattr(geohide,'_ps',lambda s:received.append(s))
    geohide._apply_one(4,['1.1.1.1'],NIC_A)
    assert len(received)==1
    assert 'Get-NetAdapter -InterfaceIndex 4' in received[0]
    assert NIC_A in received[0]
    assert 'Set-DnsClientServerAddress' in received[0]
    assert received[0].index('Get-NetAdapter') < received[0].index('Set-DnsClientServerAddress')


def test_apply_legacy_unchanged_signature(monkeypatch):
    received=[]
    monkeypatch.setattr(geohide,'_ps',lambda s:received.append(s))
    geohide._apply_one(7,None)
    assert 'Get-NetAdapter' not in received[0]


def test_apply_rejects_invalid_guid_before_shell(monkeypatch):
    monkeypatch.setattr(geohide,'_ps',lambda s:pytest.fail('PowerShell should not run'))
    with pytest.raises(ValueError):
        geohide._apply_one(4,['1.1.1.1'],"'; shutdown.exe")


def test_enable_verifies_identity_on_second_snapshot(tmp_path,monkeypatch):
    journal=tmp_path/'restore.json'
    stage=[0]
    def snapshot():
        stage[0]+=1
        # Start: original adapter. Verification: index now references a new NIC.
        return [adapter(addresses=['1.1.1.1'])] if stage[0]==1 else [adapter(guid=NIC_B,addresses=geohide.GEOHIDE_IPV4)]
    monkeypatch.setattr(geohide,'query_dns_state',snapshot)
    monkeypatch.setattr(geohide,'_apply_one',lambda *a:None)
    with pytest.raises(RuntimeError,match='Восстановление не завершено'):
        geohide.enable_dns(journal,probe=False)
    assert journal.exists()
    assert json.loads(journal.read_text())['interfaces'][0]['guid']==NIC_A


def test_restore_verification_keeps_journal_on_guid_change(tmp_path,monkeypatch):
    journal=tmp_path/'restore.json'
    geohide._save_state([adapter(addresses=('1.1.1.1',))],journal)
    phase=[0]
    def snapshot():
        phase[0]+=1
        if phase[0]==1:return [adapter(addresses=geohide.GEOHIDE_IPV4)]
        return [adapter(guid=NIC_B,addresses=['1.1.1.1'])]
    monkeypatch.setattr(geohide,'query_dns_state',snapshot)
    monkeypatch.setattr(geohide,'_apply_one',lambda *a:None)
    with pytest.raises(RuntimeError,match='Windows не подтвердил восстановление'):
        geohide.restore_dns(journal)
    assert journal.exists()


def test_dhcp_restore_refuses_manual_dns_left_by_windows(tmp_path, monkeypatch):
    journal=tmp_path/'restore.json'
    geohide._save_state([adapter(addresses=('1.1.1.1',),manual='')],journal)
    observations=[
        [adapter(addresses=geohide.GEOHIDE_IPV4,manual='')],
        [adapter(addresses=['8.8.8.8'],manual='8.8.8.8')],
    ]
    monkeypatch.setattr(geohide,'query_dns_state',lambda:observations.pop(0))
    monkeypatch.setattr(geohide,'_apply_one',lambda *a:None)
    with pytest.raises(RuntimeError,match='Windows не подтвердил восстановление'):
        geohide.restore_dns(journal)
    assert journal.exists()


def test_dhcp_restore_refuses_geo_dns_single_address(tmp_path, monkeypatch):
    journal=tmp_path/'restore.json'
    geohide._save_state([adapter(addresses=('1.1.1.1',),manual='')],journal)
    observations=[
        [adapter(addresses=geohide.GEOHIDE_IPV4,manual='')],
        [adapter(addresses=geohide.GEOHIDE_IPV4[:1],manual='')],
    ]
    monkeypatch.setattr(geohide,'query_dns_state',lambda:observations.pop(0))
    monkeypatch.setattr(geohide,'_apply_one',lambda *a:None)
    with pytest.raises(RuntimeError,match='Windows не подтвердил восстановление'):
        geohide.restore_dns(journal)
    assert journal.exists()


def test_legacy_backup_remains_readable_after_partial_restore(tmp_path,monkeypatch):
    journal=tmp_path/'restore.json'
    prior=adapter(addresses=['1.1.1.1']); prior.pop('guid')
    geohide._save_state([prior],journal)
    monkeypatch.setattr(geohide,'query_dns_state',lambda:[{'index':4,'alias':'Ethernet','before':list(geohide.GEOHIDE_IPV4),'manual':''}])
    monkeypatch.setattr(geohide,'_apply_one',lambda *a:(_ for _ in ()).throw(OSError('fail')))
    for _ in range(2):
        with pytest.raises(RuntimeError, match='не полностью'):
            geohide.restore_dns(journal)
    saved=json.loads(journal.read_text())['interfaces']
    assert 'guid' not in saved[0]


def test_snapshot_skips_only_absent_dns_cim_objects():
    """Hosted Windows can expose a NIC without DNSClient CIM state."""
    script = geohide._SNAPSHOT
    assert "Get-DnsClientServerAddress -InterfaceIndex $a.ifIndex -AddressFamily IPv4 -ErrorAction Stop" in script
    assert "CmdletizationQuery_NotFound*" in script
    assert "{ continue }" in script
    assert "    throw" in script
    assert "@($dns.ServerAddresses)" in script
