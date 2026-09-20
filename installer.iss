#ifndef AppVersion
#error AppVersion must be supplied by build_windows.ps1 from pyproject.toml
#endif
[Setup]
AppId={{81633412-E442-4940-9818-62541A2DD032}
AppName=Audio2Text
AppVersion={#AppVersion}
AppPublisher=Audio2Text
DefaultDirName={localappdata}\Programs\Audio2Text
DefaultGroupName=Audio2Text
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=release
OutputBaseFilename=Audio2Text-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\Audio2Text.exe
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\Audio2Text\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Audio2Text"; Filename: "{app}\Audio2Text.exe"
Name: "{autodesktop}\Audio2Text"; Filename: "{app}\Audio2Text.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Audio2Text.exe"; Description: "{cm:LaunchProgram,Audio2Text}"; Flags: nowait postinstall skipifsilent
