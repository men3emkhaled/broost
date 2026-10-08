; Inno Setup script for Broost POS
#ifndef ReleaseSourceDir
  #define ReleaseSourceDir "dist\BroostPOS"
#endif

[Setup]
AppId=BroostPOS.Offline
AppName=BROOST Offline
AppVersion=2.2.0
AppPublisher=Men3em Khaled
DefaultDirName={localappdata}\Programs\BROOST Offline
DisableDirPage=no
UsePreviousAppDir=no
DefaultGroupName=BROOST Offline
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=release_offline
OutputBaseFilename=Broost_Offline_Setup_2.2
SetupIconFile=logo.ico
UninstallDisplayIcon={app}\logo.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
VersionInfoCompany=Men3em Khaled
VersionInfoDescription=BROOST Offline POS

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "{#ReleaseSourceDir}\*"; DestDir: "{app}"; Excludes: "broost_pos.db,backups\*,.last_backup_date"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\BROOST Offline"; Filename: "{app}\CashierSystemGuard.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\BROOST Offline"; Filename: "{app}\CashierSystemGuard.exe"; WorkingDir: "{app}"

[Run]
Filename: "{app}\CashierSystemGuard.exe"; Description: "{cm:LaunchProgram,BROOST Offline}"; Flags: nowait postinstall skipifsilent
