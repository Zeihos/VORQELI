from vorqeli_connect import startup

def test_launch_args_regular(monkeypatch):
    monkeypatch.setattr(startup.sys,'frozen',False,raising=False)
    cmd=startup.launch_args()
    assert '--minimized' in cmd
    assert '-m' in cmd
    assert 'vorqeli_connect' in cmd

def test_launch_command_quotes_program(monkeypatch):
    monkeypatch.setattr(startup,'launch_args',lambda:['C:/Program Files/Vorqeli Connect.exe','--minimized'])
    cmd=startup.launch_command()
    assert cmd.startswith('"C:/Program Files/Vorqeli Connect.exe"')
    assert cmd.endswith('--minimized')

def test_no_elevated_task_for_source_checkout():
    assert not startup.trusted_install_path()
