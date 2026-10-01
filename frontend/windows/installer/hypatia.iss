; Built by .github/workflows/build-desktop.yml:
;   iscc /DAppVersion=0.1.0 /DBuildDir=<flutter Release dir> /DOutputDir=<dist> hypatia.iss

#ifndef AppVersion
  #error Define AppVersion, e.g. /DAppVersion=0.1.0
#endif
#ifndef BuildDir
  #error Define BuildDir as the packaged Flutter Release directory
#endif
#ifndef OutputDir
  #define OutputDir "."
#endif

[Setup]
AppId={{8F3C2A6E-5B1D-4E7A-9C42-6D1E0B7A3F95}
AppName=Hypatia
AppVersion={#AppVersion}
AppPublisher=Hypatia
DefaultDirName={autopf}\Hypatia
DisableProgramGroupPage=yes
; Per-user install by default, so no administrator prompt is needed.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename=Hypatia-{#AppVersion}-windows-x64-setup
SetupIconFile=..\runner\resources\app_icon.ico
UninstallDisplayIcon={app}\Hypatia.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; Files dropped by a newer release must not linger from the previous one.
Type: filesandordirs; Name: "{app}\backend"
Type: filesandordirs; Name: "{app}\data"

[Files]
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Hypatia"; Filename: "{app}\Hypatia.exe"
Name: "{autodesktop}\Hypatia"; Filename: "{app}\Hypatia.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Hypatia.exe"; Description: "{cm:LaunchProgram,Hypatia}"; Flags: nowait postinstall skipifsilent
