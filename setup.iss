; Inno Setup script for Broost POS
#ifndef ReleaseSourceDir
  #define ReleaseSourceDir "dist\BroostPOS"
#endif

[Setup]
AppId=Broost POS
AppName=نظام الكاشير
AppVersion=1.0
AppPublisher=Cashier System
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

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#ReleaseSourceDir}\*"; DestDir: "{app}"; Excludes: "broost_pos.db,backups\*,.last_backup_date,web_data\*"; Flags: recursesubdirs createallsubdirs
Source: "{#ReleaseSourceDir}\broost_pos.db"; DestDir: "{app}"; Flags: onlyifdoesntexist

[Icons]
Name: "{group}\نظام الكاشير"; Filename: "{app}\BroostPOS.exe"
Name: "{group}\Broost Web Server"; Filename: "{app}\BroostWebServer.exe"; WorkingDir: "{app}"
Name: "{group}\Broost Website"; Filename: "http://127.0.0.1:8765"
Name: "{group}\Broost Admin"; Filename: "http://127.0.0.1:8765/admin"
Name: "{userdesktop}\نظام الكاشير"; Filename: "{app}\BroostPOS.exe"; Tasks: desktopicon; WorkingDir: "{app}"

[Run]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Broost Website - Local Router"""; Flags: runhidden
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""Broost Website - Local Router"" dir=in action=allow protocol=TCP localport=8765 profile=private remoteip=localsubnet"; Flags: runhidden
Filename: "{app}\BroostWebServer.exe"; Description: "تشغيل موقع Broost على الجهاز والشبكة المحلية"; Flags: nowait runhidden skipifsilent
Filename: "{app}\BroostPOS.exe"; Description: "{cm:LaunchProgram,نظام الكاشير}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Broost Website - Local Router"""; Flags: runhidden; RunOnceId: "RemoveBroostLocalNetworkRule"
