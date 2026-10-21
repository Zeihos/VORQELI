#define MyAppName "VORQELI Connect"
#define MyAppVersion "0.40.0"
#define MyAppExeName "VORQELI-Connect.exe"

[Setup]
AppId={{8B7F7AA4-81DB-4EDC-86F6-94D7531026BC}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=VORQELI Contributors
; Prevent an update while the networking application is still running in the tray.
AppMutex=Local\VORQELI-Connect-Instance
AppPublisherURL=https://github.com/Zeihos/VORQELI
DefaultDirName={autopf}\VORQELI Connect
DefaultGroupName=VORQELI Connect
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=VORQELI-Connect-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=..\assets\VORQELI.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

[Files]
Source: "..\dist\VORQELI-Connect.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\NOTICE.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\docs\QUICK_START.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\VORQELI Connect"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\VORQELI Connect"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительные параметры:"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить VORQELI Connect"; Flags: nowait postinstall skipifsilent


[Code]
// Preflight runs while files still exist. Failure aborts uninstallation.
// This prevents removing the cleanup executable with DNS changes pending.
function InitializeUninstall(): Boolean;
var
  ExitCode: Integer;
  Started: Boolean;
begin
  Result := False;
  Started := Exec(ExpandConstant('{app}\{#MyAppExeName}'),
    '--uninstall-cleanup', ExpandConstant('{app}'), SW_HIDE,
    ewWaitUntilTerminated, ExitCode);
  if not Started then
  begin
    Log('VORQELI: cleanup helper could not start; uninstall denied.');
    if not UninstallSilent() then
      MsgBox('Не удалось запустить проверку перед удалением VORQELI. ' +
        'Файлы не будут удалены.', mbError, MB_OK);
    Exit;
  end;
  if ExitCode <> 0 then
  begin
    Log('VORQELI: cleanup returned ' + IntToStr(ExitCode) +
      '; uninstall denied.');
    if not UninstallSilent() then
      MsgBox('Не удалось безопасно подготовить удаление VORQELI. ' +
        'Полностью закройте программу через трей и восстановите DNS и HOSTS (GeoHide RU / VORQELI). ' +
        'Если проблема осталась, запустите VORQELI от администратора ' +
        'и повторите удаление. Код: ' + IntToStr(ExitCode), mbError, MB_OK);
    Exit;
  end;
  Result := True;
end;
