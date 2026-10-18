"""Non-mutating Windows CI check of the native DoH PowerShell capability.

Does NOT enable or configure DNS, network adapters or global DoH mappings.
Windows Server runners can differ from consumer Windows 11; unavailable
cmdlets are reported as unsupported, not as a build failure.
"""
from __future__ import annotations
import json
import os
import subprocess

CMDS=('Get-DnsClientDohServerAddress','Add-DnsClientDohServerAddress',
      'Remove-DnsClientDohServerAddress')


def check() -> dict:
    if os.name != 'nt':
        return {'platform': 'other', 'native_doh_cmdlets_available': False}
    ps = ("$x = @('" + "','".join(CMDS) + "'); "
          "$found = @($x | ForEach-Object { [bool](Get-Command $_ -ErrorAction SilentlyContinue) }); "
          "[bool](-not ($found -contains $False))")
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',ps],
                          capture_output=True,text=True,timeout=20,
                          creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:
        raise RuntimeError('Windows DoH preflight failed')
    value=result.stdout.strip().lower()
    if value not in ('true','false'):
        raise RuntimeError('Windows DoH preflight returned an invalid value')
    return {'platform':'windows','native_doh_cmdlets_available':value=='true'}


if __name__=='__main__':
    print(json.dumps(check(),ensure_ascii=False,sort_keys=True))
