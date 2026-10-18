import json
from pathlib import Path
import pytest
from vorqeli_connect import geohide


def test_validate_snapshot_rejects_bad_index():
    with pytest.raises(ValueError):
        geohide._validate_state([{'index':'echo hello','manual':'','before':[]}])


def test_enable_backup_restore(tmp_path,monkeypatch):
    state=tmp_path/'backup.json'
    sample=[{'index':3,'alias':'Ethernet','manual':'1.1.1.1,8.8.8.8','before':['1.1.1.1','8.8.8.8']}]
    used=[]
    current_ips = list(sample[0]['before'])
    def snapshot():
        return [{'index':3,'alias':'Ethernet','manual':'1.1.1.1,8.8.8.8','before':list(current_ips)}]
    def apply(index, addresses):
        used.append((index, addresses))
        current_ips[:] = addresses or sample[0]['before']
    monkeypatch.setattr(geohide,'query_dns_state',snapshot)
    monkeypatch.setattr(geohide,'_apply_one',apply)
    assert geohide.enable_dns(state,probe=False)==1
    assert used==[(3,list(geohide.GEOHIDE_IPV4))]
    assert state.exists()
    assert geohide.restore_dns(state)
    assert used[-1]==(3,['1.1.1.1','8.8.8.8'])
    assert not state.exists()


def test_restore_does_not_override_external_changes(tmp_path,monkeypatch):
    state=tmp_path/'backup.json'
    geohide._save_state([{'index':5,'manual':'','alias':'Wi-Fi','before':['9.9.9.9']}],state)
    monkeypatch.setattr(geohide,'query_dns_state',lambda:[{'index':5,'manual':'4.4.4.4','alias':'Wi-Fi','before':['4.4.4.4']}])
    actions=[]
    monkeypatch.setattr(geohide,'_apply_one',lambda *args:actions.append(args))
    with pytest.raises(RuntimeError,match='другой программой'):
        geohide.restore_dns(state)
    assert state.exists()
    assert actions==[]


def test_doh_probe_rejects_bad_packet(monkeypatch):
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,n):return b'not dns'
    monkeypatch.setattr(geohide.urllib.request,'urlopen',lambda *a,**kw:Response())
    with pytest.raises(RuntimeError):geohide._dns_probe()
