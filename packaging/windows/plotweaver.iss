; Voxprint AI Plotweaver. Small online installer: sources plus a runtime script.
; Python 3.14 is downloaded on first launch of the script, not bundled.
; Start menu group is Voxprint. Windows 11 24H2 is the minimum.

#define MyAppName "Voxprint AI Plotweaver"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Aleksandr Mitroshenkov"
#define MyAppURL "https://github.com/Mitroshenkov87/voxprint-plotweaver"

[Setup]
AppId={{A7C3E1B2-4F58-4D1A-9C6E-2B8F0A41D6E3}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={localappdata}\Voxprint\Plotweaver
DefaultGroupName=Voxprint
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=VoxprintPlotweaver-{#MyAppVersion}-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.26100
UninstallDisplayIcon={app}\branding\plotweaver.ico
UninstallDisplayName={#MyAppName}

[Files]
Source: "..\..\src\*"; DestDir: "{app}\src"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\bakeoff\*"; DestDir: "{app}\bakeoff"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\scenarios\*"; DestDir: "{app}\scenarios"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\docs\*"; DestDir: "{app}\docs"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\branding\*"; DestDir: "{app}\branding"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\scripts\*"; DestDir: "{app}\scripts"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\pyproject.toml"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\NOTICE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\BUILD.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "install-runtime.ps1"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\.venv\Scripts\pythonw.exe"; Parameters: "-m plotweaver gui"; WorkingDir: "{app}"; IconFilename: "{app}\branding\plotweaver.ico"

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\install-runtime.ps1"""; StatusMsg: "Installing Python 3.14 and Plotweaver"; Flags: runhidden waituntilterminated

[UninstallDelete]
Type: filesandordirs; Name: "{app}\.venv"
