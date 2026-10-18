from pathlib import Path
import subprocess
import pytest
from vorqeli_connect.process_manager import ModuleManager

def test_invalid_extension(tmp_path):
    f=tmp_path/"test.txt";f.write_text("x")
    with pytest.raises(ValueError):ModuleManager().start(f)

def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):ModuleManager().start(tmp_path/"missing.exe")

def test_process_lifecycle(tmp_path, monkeypatch):
    f=tmp_path/"module.exe";f.write_bytes(b"test")
    class Fake:
        pid=42
        def __init__(self):self.active=True
        def poll(self):return None if self.active else 0
        def terminate(self):self.active=False
        def wait(self,timeout):return 0
    fake=Fake()
    monkeypatch.setattr(subprocess,"Popen",lambda *a,**kw:fake)
    m=ModuleManager()
    assert m.start(f)==42
    assert m.running
    with pytest.raises(RuntimeError):m.start(f)
    assert m.stop()
    assert not m.running
    assert not m.stop()
