; Voxprint AI Plotweaver. Full installer: the app, Python 3.14, dependencies,
; and the pinned llama.cpp b11476 Vulkan runtime. After the files are copied,
; provision installs anything still missing into %LOCALAPPDATA%\Voxprint\shared.
; Start menu group is Voxprint. Windows 11 24H2 is the minimum.

#ifndef MyAppVersion
  #error BUILD.json supplies MyAppVersion. packaging/windows/build-installer.ps1 passes /DMyAppVersion.
#endif
#ifndef StageDir
  #define StageDir "..\..\build\stage"
#endif

#define MyAppName "Voxprint AI Plotweaver"
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
OutputBaseFilename=VoxprintPlotweaver-{#MyAppVersion}-win64-setup
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
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "__pycache__\*,*.pyc"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m plotweaver gui"; WorkingDir: "{app}"; IconFilename: "{app}\branding\plotweaver.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m plotweaver gui"; WorkingDir: "{app}"; IconFilename: "{app}\branding\plotweaver.ico"

[Run]
Filename: "{app}\plotweaver-provision.cmd"; StatusMsg: "Installing shared Voxprint files..."; Flags: waituntilterminated

[UninstallRun]
Filename: "{app}\python\python.exe"; Parameters: "-m plotweaver release-shared"; Flags: waituntilterminated skipifdoesntexist
