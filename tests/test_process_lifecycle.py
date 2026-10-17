from vorqeli_connect.engine_processes import EngineProcess
from vorqeli_connect.engine_adapters import LaunchSpec


def test_runner_run_token_and_log_rotation(tmp_path, monkeypatch):
    class FakeProc:
        pid=1234
        code=None
        def poll(self): return self.code
        def terminate(self): self.code=0
        def wait(self,timeout): return self.code
        def kill(self): self.code=-9
    fake=FakeProc()
    monkeypatch.setattr("subprocess.Popen",lambda *args,**kwargs: fake)
    log=tmp_path/"output.log"
    log.write_bytes(b"x"*(2*1024*1024))
    runner=EngineProcess("Test")
    initial=runner.run_id
    runner.start(LaunchSpec(("x.exe",),tmp_path,"Test"),log)
    assert runner.run_id==initial+1
    assert (tmp_path/"output.log.old").exists()
    runner.stop()
    assert runner.run_id==initial+2


def test_exit_closes_file(tmp_path,monkeypatch):
    class FakeProc:
        pid=2
        def poll(self): return 1
    monkeypatch.setattr("subprocess.Popen",lambda *args,**kwargs: FakeProc())
    runner=EngineProcess("Test")
    runner.start(LaunchSpec(("x.exe",),tmp_path,"Test"),tmp_path/"log")
    assert runner._log_handle is not None
    assert not runner.running
    assert runner._log_handle is None
