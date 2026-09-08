#ifndef ReleaseSourceDir
  #define ReleaseSourceDir "dist\BroostPOS"
#endif
[Setup]
AppId=Broost POS
AppName=بروست - الكاشير السحابي
AppVersion=2.0
AppPublisher=Men3em Khaled
DefaultDirName={userappdata}\Programs\Cashier System
DefaultGroupName=بروست
PrivilegesRequired=lowest
OutputBaseFilename=BroostPOS_Cloud_2.0
SetupIconFile=logo.ico
UninstallDisplayIcon={app}\logo.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
[Files]
Source: "{#ReleaseSourceDir}\*"; DestDir: "{app}"; Excludes: "*.db,*.env,backups\*,web_data\*"; Flags: recursesubdirs createallsubdirs
[InstallDelete]
Type: files; Name: "{app}\_internal\icuuc.dll"
Type: files; Name: "{app}\_internal\icuin.dll"
Type: files; Name: "{app}\_internal\ucrtbase.dll"
Type: files; Name: "{app}\_internal\api-ms-win-*.dll"
[Icons]
Name: "{group}\بروست"; Filename: "{app}\BroostPOS.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\نظام الكاشير"; Filename: "{app}\BroostPOS.exe"; WorkingDir: "{app}"
[Run]
Filename: "{app}\BroostPOS.exe"; Description: "تشغيل الكاشير السحابي"; Flags: nowait postinstall skipifsilent
