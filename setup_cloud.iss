#ifndef ReleaseSourceDir
  #define ReleaseSourceDir "dist\BroostPOS"
#endif
[Setup]
AppId=Broost POS
AppName=بروست - الكاشير السحابي
AppVersion=2.1
AppPublisher=Men3em Khaled
DefaultDirName={userappdata}\Programs\Cashier System
DefaultGroupName=بروست
PrivilegesRequired=lowest
OutputBaseFilename=BroostPOS_Cloud_2.1_Advanced
SetupIconFile=logo.ico
UninstallDisplayIcon={app}\logo.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
AppMutex=Local\BroostCloudPOS
ArchitecturesAllowed=x64compatible
MinVersion=10.0.19045
ExtraDiskSpaceRequired=1073741824
DisableProgramGroupPage=yes
SetupLogging=yes
[Languages]
Name: "arabic"; MessagesFile: "compiler:Languages\Arabic.isl"
[Tasks]
Name: "desktopicon"; Description: "إنشاء اختصار الكاشير على سطح المكتب"; Flags: checkedonce
[Files]
Source: "{#ReleaseSourceDir}\*"; DestDir: "{app}"; Excludes: "*.db,*.env,backups\*,web_data\*"; Flags: recursesubdirs createallsubdirs
[InstallDelete]
Type: files; Name: "{app}\_internal\icuuc.dll"
Type: files; Name: "{app}\_internal\icuin.dll"
Type: files; Name: "{app}\_internal\ucrtbase.dll"
Type: files; Name: "{app}\_internal\api-ms-win-*.dll"
; Retire local-server launchers without touching any database or backup.
Type: files; Name: "{app}\CashierSystemGuard.exe"
Type: files; Name: "{app}\BroostWebServer.exe"
[Icons]
Name: "{group}\بروست"; Filename: "{app}\BroostPOS.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\نظام الكاشير"; Filename: "{app}\BroostPOS.exe"; WorkingDir: "{app}"; Tasks: desktopicon
[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "BroostCloudPOS"; Flags: uninsdeletevalue
[Run]
Filename: "{app}\BroostPOS.exe"; Description: "تجهيز جهاز المطعم وتشغيل الكاشير"; Flags: nowait postinstall skipifsilent
[Code]
procedure InitializeWizard;
var
  InfoPage: TOutputMsgWizardPage;
begin
  InfoPage := CreateOutputMsgPage(wpWelcome, 'تجهيز جهاز المطعم',
    'تثبيت الكاشير السحابي مع فحص التشغيل',
    'بعد التثبيت سيظهر معالج التجهيز بالعربي:' + #13#10 + #13#10 +
    '1. فحص الجهاز والصلاحيات والمساحة.' + #13#10 +
    '2. اختبار السيرفر ورمز الكاشير وتحميل المنيو.' + #13#10 +
    '3. اختيار الطابعة ومقاس الورق وطباعة ورقة اختبار.' + #13#10 +
    '4. إعداد اسم الجهاز والتشغيل مع Windows وملء الشاشة.' + #13#10 + #13#10 +
    'جهّز رمز الكاشير ووصل الطابعة وثبّت تعريفها قبل أول تشغيل.' + #13#10 +
    'التثبيت لا يستورد بيانات قديمة ولا يمسح بيانات المطعم السحابية.');
end;
