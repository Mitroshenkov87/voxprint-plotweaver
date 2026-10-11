; VOXPrint AI Plotweaver. Full installer: the app, Python 3.14, dependencies,
; and the pinned llama.cpp b11476 Vulkan runtime. Files go in
; C:\Program Files\VOXPrint AI Suite\Plotweaver. Setup then runs
; voxprint-mdl download --app plotweaver --json. A silent install logs that
; download and does not open a window. A failed download does not fail setup.
; Windows 11 24H2 is the minimum.

#ifndef MyAppVersion
  #error BUILD.json supplies MyAppVersion. packaging/windows/build-installer.ps1 passes /DMyAppVersion.
#endif
#ifndef StageDir
  #define StageDir "..\..\build\stage"
#endif

#define MyAppName "VOXPrint AI Plotweaver"
#define MyAppPublisher "Aleksandr Mitroshenkov"
#define MyAppURL "https://github.com/Mitroshenkov87/voxprint-plotweaver"

[Setup]
AppId={{A7C3E1B2-4F58-4D1A-9C6E-2B8F0A41D6E3}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={autopf}\VOXPrint AI Suite\Plotweaver
DisableDirPage=yes
UsePreviousAppDir=no
DefaultGroupName=VOXPrint AI Suite
DisableProgramGroupPage=yes
UsePreviousGroup=no
ChangesEnvironment=yes
OutputDir=Output
OutputBaseFilename=VoxprintPlotweaver-{#MyAppVersion}-win64-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.26100
UninstallDisplayIcon={app}\branding\plotweaver.ico
UninstallDisplayName={#MyAppName}

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "__pycache__\*,*.pyc"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\voxprint-plotweaver.exe"; WorkingDir: "{app}"; IconFilename: "{app}\branding\plotweaver.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\voxprint-plotweaver.exe"; WorkingDir: "{app}"; IconFilename: "{app}\branding\plotweaver.ico"

[Registry]
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Check: NeedsAddPath('{app}')

[Run]
Filename: "{app}\python\python.exe"; Parameters: "-m plotweaver mdl-progress --installer"; StatusMsg: "Downloading models..."; Flags: waituntilterminated; Check: not WizardSilent
Filename: "{app}\python\python.exe"; Parameters: "-m plotweaver mdl-progress --quiet --installer"; StatusMsg: "Downloading models..."; Flags: runhidden waituntilterminated; Check: WizardSilent
Filename: "{app}\voxprint-plotweaver.exe"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: postinstall skipifsilent nowait

[UninstallRun]
Filename: "{app}\python\python.exe"; Parameters: "-m plotweaver release-shared"; Flags: waituntilterminated skipifdoesntexist

[Code]
function NeedsAddPath(Param: string): boolean;
var
  OrigPath: string;
begin
  if not RegQueryStringValue(HKEY_LOCAL_MACHINE,
    'SYSTEM\CurrentControlSet\Control\Session Manager\Environment',
    'Path', OrigPath)
  then begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Uppercase(Param) + ';', ';' + Uppercase(OrigPath) + ';') = 0;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  OldDir: string;
begin
  if CurStep <> ssPostInstall then
    exit;
  { Drop the previous program folder. Do not run its uninstaller: that would
    release shared models. User data under %LOCALAPPDATA%\Voxprint stays. }
  OldDir := ExpandConstant('{localappdata}\Voxprint\Plotweaver');
  if CompareText(OldDir, ExpandConstant('{app}')) <> 0 then
    DelTree(OldDir, True, True, True);
  DeleteFile(ExpandConstant('{userdesktop}\Voxprint AI Plotweaver.lnk'));
  DeleteFile(ExpandConstant('{userprograms}\Voxprint\Voxprint AI Plotweaver.lnk'));
  RemoveDir(ExpandConstant('{userprograms}\Voxprint'));
  RegDeleteKeyIncludingSubkeys(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{A7C3E1B2-4F58-4D1A-9C6E-2B8F0A41D6E3}_is1');
end;
