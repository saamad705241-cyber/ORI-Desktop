#ifndef MyAppVersion
  #define MyAppVersion "3.6.2"
#endif

#define MyAppName "ORI"
#define MyAppPublisher "Abdul Samad"
#define MyAppExeName "ORI.exe"
#define MyAppId "{{B2A1DF41-8D63-4B27-9B78-64A8B52C9A1E}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\ORI
DefaultGroupName=ORI
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64
MinVersion=10.0
WizardStyle=modern
WizardSizePercent=110
SetupIconFile=..\config\ori.ico
UninstallDisplayIcon={app}\ORI.exe
UninstallDisplayName=ORI Personal AI Desktop Assistant
Uninstallable=yes
CloseApplications=yes
RestartApplications=no
Compression=lzma2/ultra64
SolidCompression=yes
OutputDir=..\dist\installer
OutputBaseFilename=ORI-Setup-{#MyAppVersion}
VersionInfoVersion={#MyAppVersion}
VersionInfoProductName=ORI
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=ORI Personal AI Desktop Assistant Setup
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\ORI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "config\api_keys.json"

[Icons]
Name: "{autoprograms}\ORI"; Filename: "{app}\ORI.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\ORI"; Filename: "{app}\ORI.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\ORI.exe"; Description: "Launch ORI"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent
