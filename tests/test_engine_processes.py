import subprocess
import pytest
from pathlib import Path
from vorqeli_connect.engine_processes import EngineProcess
from vorqeli_connect.engine_adapters import LaunchSpec

class FakeProc:
    def __init__(self):
        self.pid=3432
        self.active=True
        self.code=0
        self.killed=False
    def poll(self):
        return None if self.active else self.code
    def terminate(self):
        self.active=False
    def wait(self,timeout):
        return self.code
    def kill(self):
        self.killed=True
        self.active=False


def test_engine_launch_and_stop(tmp_path, monkeypatch):
    fake=FakeProc()
    params={}
    def launch(argv, **kwargs):
        params.update(argv=argv, **kwargs)
        return fake
    monkeypatch.setattr(subprocess,"Popen",launch)
    runner=EngineProcess("Test")
    spec=LaunchSpec(("test.exe","--flag","a b"),tmp_path,"Test")
    assert runner.start(spec,tmp_path/"engine.log") ==3432
    assert params["shell"] is False
    assert params["argv"]==["test.exe","--flag","a b"]
    assert runner.running and runner.pid==3432
    with pytest.raises(RuntimeError): runner.start(spec,tmp_path/"other.log")
    assert runner.stop()
    assert not runner.running
    assert runner.exit_code ==0
    assert not runner.stop()


def test_engine_failed_launch_closes_log(tmp_path,monkeypatch):
    def broken(*args,**kwargs):
        raise OSError("nope")
    monkeypatch.setattr(subprocess,"Popen",broken)
    runner=EngineProcess("Test")
    with pytest.raises(OSError):
        runner.start(LaunchSpec(("missing.exe",),tmp_path,"x"),tmp_path/"engine.log")
    assert not runner.running
    assert runner._log_handle is None


def test_engine_kill_on_timeout(tmp_path,monkeypatch):
    fake=FakeProc()
    calls=[0]
    def wait(timeout):
        calls[0]+=1
        if calls[0]==1: raise subprocess.TimeoutExpired("prog",timeout)
        return 0
    fake.wait=wait
    monkeypatch.setattr(subprocess,"Popen",lambda *args,**kwargs:fake)
    runner=EngineProcess("Test")
    runner.start(LaunchSpec(("test.exe",),tmp_path,"x"),tmp_path/"test.log")
    assert runner.stop()
    assert fake.killed
