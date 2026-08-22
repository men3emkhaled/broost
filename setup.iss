; Inno Setup script for Broost POS
#ifndef ReleaseSourceDir
  #define ReleaseSourceDir "dist\BroostPOS"
#endif

[Setup]
AppId=Broost POS
AppName=نظام الكاشير
AppVersion=1.2
AppPublisher=Men3em Khaled
DefaultDirName={userappdata}\Programs\Cashier System
DefaultGroupName=نظام الكاشير
DisableProgramGroupPage=yes
PrivilegesRequired=admin
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
Source: "{#ReleaseSourceDir}\broost_pos.db"; DestDir: "{app}"; Flags: onlyifdoesntexist

[Icons]
Name: "{group}\نظام الكاشير"; Filename: "{app}\CashierSystemGuard.exe"
Name: "{group}\الموقع المحلي"; Filename: "http://127.0.0.1:8765"
Name: "{group}\لوحة إدارة الموقع"; Filename: "http://127.0.0.1:8765/admin"
Name: "{userdesktop}\نظام الكاشير"; Filename: "{app}\CashierSystemGuard.exe"; WorkingDir: "{app}"

[Run]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Broost Website - Local Router"""; Flags: runhidden
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""Broost Website - Local Router"" dir=in action=allow protocol=TCP localport=8765 profile=private remoteip=localsubnet"; Flags: runhidden
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Cashier System - HTTPS Sync"""; Flags: runhidden
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""Cashier System - HTTPS Sync"" dir=out action=allow program=""{app}\BroostPOS.exe"" protocol=TCP remoteport=443 profile=any"; Flags: runhidden
Filename: "{app}\BroostWebServer.exe"; Description: "تشغيل الموقع المحلي على الجهاز والشبكة المحلية"; Flags: nowait runhidden skipifsilent
Filename: "{app}\CashierSystemGuard.exe"; Description: "{cm:LaunchProgram,نظام الكاشير}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Broost Website - Local Router"""; Flags: runhidden; RunOnceId: "RemoveBroostLocalNetworkRule"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Cashier System - HTTPS Sync"""; Flags: runhidden; RunOnceId: "RemoveCashierHttpsSyncRule"
