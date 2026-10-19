"""Offline regression checks for silent Inno Setup uninstallation.

Checks source contracts only: no app launches, registry changes, or DNS writes.
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def test_preflight_failure_does_not_open_modal_dialog_during_silent_uninstall():
    iss = (ROOT / 'installer/VORQELI.iss').read_text(encoding='utf-8')
    assert 'Result := False;' in iss
    assert 'Result := True;' in iss
    assert "'--uninstall-cleanup'" in iss
    assert 'ewWaitUntilTerminated' in iss

    # Both preflight failure paths must remain fail-closed, but only
    # interactive uninstallations may show a blocking message box.
    for condition in ('if not Started then', 'if ExitCode <> 0 then'):
        match = re.search(
            re.escape(condition) + r'\s*begin\s*(.*?)\s*end;',
            iss, flags=re.DOTALL,
        )
        assert match, condition
        block = match.group(1)
        assert 'Log(' in block
        assert re.search(r'if not UninstallSilent\(\) then\s*MsgBox\(', block)
        assert block.rstrip().endswith('Exit;')

    assert iss.count('MsgBox(') == 2
    assert iss.count('if not UninstallSilent() then') == 2


def test_windows_smoke_preserves_blocked_removal_and_final_cleanup():
    smoke = (ROOT / 'scripts/windows_installer_smoke.ps1').read_text(encoding='utf-8')
    assert "SMOKE START: " in smoke
    assert "-Label 'blocked-cleanup-check'" in smoke
    assert "-Label 'blocked-uninstall'" in smoke
    assert "'vorqeli-smoke-blocked-uninstall.log'" in smoke
    assert '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LOG=' in smoke
    assert 'if ($blockedRemoval.ExitCode -eq 0)' in smoke
    assert "'Blocked uninstall removed the installed executable'" in smoke
    assert '$mutex.Dispose()' in smoke
    assert "-Label 'final-uninstall'" in smoke
