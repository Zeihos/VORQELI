#define MyAppName "VORQELI Connect"
#define MyAppVersion "0.12.0"
#define MyAppExeName "VORQELI-Connect.exe"

[Setup]
AppId={{8B7F7AA4-81DB-4EDC-86F6-94D7531026BC}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=VORQELI Contributors
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

[UninstallRun]
Filename: "{app}\{#MyAppExeName}"; Parameters: "--uninstall-cleanup"; Flags: runhidden waituntilterminated
