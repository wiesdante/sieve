; Inno Setup script for the Sieve installer.
; Build: ISCC.exe /DAppVersion=1.2.3 installer\sieve.iss
; Expects the PyInstaller output in dist\Sieve.

#define AppName "Sieve"
#define AppExe "Sieve.exe"
#define AppPublisher "wiesdante"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
; AppId identifies the installation for upgrades. Never change it.
AppId={{4C79EACF-60FA-417D-85D8-06774D0074D3}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL=https://github.com/wiesdante
VersionInfoVersion={#AppVersion}
VersionInfoProductName={#AppName}
; Per-user install: no administrator rights needed, so updates run silently.
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
OutputDir=..\dist\installer
OutputBaseFilename=Sieve-Setup-{#AppVersion}
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=force
RestartApplications=no

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; Remove the previous build's bundled files so stale libraries never linger.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\Sieve\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
; Also runs after silent updates, so the new version starts automatically.
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall
