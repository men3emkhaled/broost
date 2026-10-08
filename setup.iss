; Inno Setup script for Broost POS
#ifndef ReleaseSourceDir
  #define ReleaseSourceDir "dist\BroostPOS"
#endif

[Setup]
AppId=Broost POS
AppName=نظام الكاشير
AppVersion=2.2
AppPublisher=Men3em Khaled
DefaultDirName={userappdata}\Programs\Cashier System
DefaultGroupName=نظام الكاشير
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=.
OutputBaseFilename=CashierSystem_Setup
SetupIconFile=logo.ico
UninstallDisplayIcon={app}\logo.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
VersionInfoCompany=Men3em Khaled
VersionInfoDescription=نظام الكاشير

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "{#ReleaseSourceDir}\*"; DestDir: "{app}"; Excludes: "broost_pos.db,backups\*,.last_backup_date,web_data\*"; Flags: recursesubdirs createallsubdirs

[InstallDelete]
; Old bundles could shadow Windows DLLs and prevent Qt from starting after an update.
Type: files; Name: "{app}\_internal\icuuc.dll"
Type: files; Name: "{app}\_internal\icuin.dll"
Type: files; Name: "{app}\_internal\ucrtbase.dll"
Type: files; Name: "{app}\_internal\api-ms-win-*.dll"

[Icons]
Name: "{group}\نظام الكاشير"; Filename: "{app}\CashierSystemGuard.exe"
Name: "{userdesktop}\نظام الكاشير"; Filename: "{app}\CashierSystemGuard.exe"; WorkingDir: "{app}"

[Run]
Filename: "{app}\CashierSystemGuard.exe"; Description: "{cm:LaunchProgram,نظام الكاشير}"; Flags: nowait postinstall skipifsilent
