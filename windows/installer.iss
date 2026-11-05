; Per-user installer: no administrator rights, installs to %LOCALAPPDATA%\Programs.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{8F3C2A51-6B1E-4C2D-9E7A-BA1E0D35C0DE}
AppName=Bale Desktop
AppVerName=Bale Desktop {#AppVersion}
AppVersion={#AppVersion}
AppPublisher=Bale Desktop (unofficial)
AppPublisherURL=https://github.com/mohammadtondar/bale-desktop
DefaultDirName={localappdata}\Programs\BaleDesktop
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist-win
OutputBaseFilename=bale-desktop_{#AppVersion}_windows-setup
SetupIconFile=bale.ico
UninstallDisplayIcon={app}\BaleDesktop.exe
UninstallDisplayName=Bale Desktop
LicenseFile=..\LICENSE
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
ArchitecturesInstallIn64BitMode=x64compatible arm64

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "Start Bale in the background when I sign in (for notifications)"; Flags: unchecked

[Files]
Source: "..\out\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{userprograms}\Bale Desktop"; Filename: "{app}\BaleDesktop.exe"
Name: "{userdesktop}\Bale Desktop"; Filename: "{app}\BaleDesktop.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "BaleDesktop"; ValueData: """{app}\BaleDesktop.exe"" --background"; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\BaleDesktop.exe"; Description: "{cm:LaunchProgram,Bale Desktop}"; Flags: nowait postinstall skipifsilent
