"""Native cloud cashier shell: no local order database or sync worker."""
import json
import os
import sys
import uuid
from pathlib import Path

from PyQt6.QtCore import QFile, QIODevice, QObject, QSettings, QUrl, QTimer, Qt, pyqtSlot
from PyQt6.QtGui import QAction, QDesktopServices, QIcon
from PyQt6.QtWidgets import QApplication, QMainWindow, QMessageBox, QDialog
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineScript
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel

from core.pos_defaults import load_pos_defaults
from core import config
from core.cloud_setup import SetupWizard, apply_print_settings, setup_required
from core.cloud_theme import apply_cloud_theme


class Printer(QObject):
    @pyqtSlot(str)
    def printHtml(self, html):
        if len(html)>200000:
            return
        from core.printing import print_text_to_printer
        print_text_to_printer(html, self.parent())


class CloudPage(QWebEnginePage):
    def __init__(self, profile, origin, parent):
        super().__init__(profile,parent)
        self.origin=origin

    def acceptNavigationRequest(self,url,kind,isMainFrame):
        if not isMainFrame:
            return True
        return url.toString()=='about:blank' or (url.scheme(),url.host(),url.port())==self.origin


class CloudWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('بروست — الكاشير السحابي')
        self.resize(1440,900)
        defaults=load_pos_defaults()
        self.defaults=defaults
        self.settings=QSettings('Broost','CloudPOS')
        # A separate INI file is used only by the explicitly requested localhost smoke test.
        self.smoke = '--setup-smoke' in sys.argv and QUrl(defaults['server_url']).host() in ('127.0.0.1','localhost')
        if self.smoke:
            self.settings=QSettings(os.environ['BROOST_SMOKE_SETTINGS'],QSettings.Format.IniFormat)
        self.settings_dir=Path(self.settings.fileName()).parent if self.smoke else Path(os.getenv('LOCALAPPDATA',str(Path.home())))/'Broost'/'CloudPOS'
        terminal=self.settings.value('terminal','') or str(uuid.uuid4())
        self.settings.setValue('terminal',terminal)
        self.url=QUrl(defaults['server_url']+'/pos')
        if self.url.scheme()!='https' and self.url.host() not in ('127.0.0.1','localhost'):
            raise RuntimeError('Cloud cashier requires HTTPS')
        # An unnamed profile is off-the-record: no persistent web cache,
        # cookies, order store or offline queue is created on this computer.
        self.profile=QWebEngineProfile(self)
        self.view=QWebEngineView(self)
        self.page=CloudPage(self.profile,(self.url.scheme(),self.url.host(),self.url.port()),self.view)
        self.view.setPage(self.page)
        self.setCentralWidget(self.view)
        self.channel=QWebChannel(self.page)
        self.printer=Printer(self)
        self.channel.registerObject('printer',self.printer)
        self.page.setWebChannel(self.channel)
        resource=QFile(':/qtwebchannel/qwebchannel.js')
        resource.open(QIODevice.OpenModeFlag.ReadOnly)
        channel_js=bytes(resource.readAll()).decode();resource.close()
        script=QWebEngineScript()
        script.setName('Broost trusted cashier')
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        script.setRunsOnSubFrames(False)
        script.setSourceCode('window.BROOST_POS_TERMINAL_ID='+json.dumps(terminal)+';window.BROOST_POS_DEVICE_KEY='+json.dumps(defaults['sync_key'])+';\n'+channel_js+'\nnew QWebChannel(qt.webChannelTransport,c=>{window.broostPrinter=c.objects.printer;});')
        self.page.scripts().insert(script)
        self.page.newWindowRequested.connect(self.external_window)
        apply_print_settings(self.settings)
        toolbar=self.addToolBar('بروست')
        toolbar.setMovable(False)
        setup_action=QAction('تجهيز الجهاز / فحص وإصلاح',self)
        setup_action.triggered.connect(self.run_setup);toolbar.addAction(setup_action)
        reload_action=QAction('إعادة الاتصال',self)
        reload_action.triggered.connect(self.reload_page);toolbar.addAction(reload_action)
        self.view.loadFinished.connect(self.loaded)
        full_action=QAction('ملء الشاشة (F11)',self)
        full_action.setShortcut('F11');full_action.triggered.connect(self.toggle_fullscreen)
        self.addAction(full_action);toolbar.addAction(full_action)
        self.started=False
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        QTimer.singleShot(0,self.start)

    def start(self):
        if setup_required(self.settings,self.defaults):
            self.run_setup()
            if not self.started:
                self.close()
        else:
            self.start_cashier()

    def start_cashier(self):
        self.started=True
        self.setWindowTitle(self.settings.value('device_name','كاشير المطعم')+' — بروست السحابي')
        if self.settings.value('fullscreen',False,type=bool):self.showFullScreen()
        else:self.showMaximized()
        self.view.setUrl(self.url)

    def run_setup(self):
        # A modal dialog preserves the current web session and unsaved cart.
        wizard=SetupWizard(self.settings,self.defaults,self.settings_dir,self)
        if self.smoke:
            from core.cloud_setup_smoke import drive_wizard
            drive_wizard(wizard)
        if wizard.exec()==QDialog.DialogCode.Accepted:
            if not self.started:self.start_cashier()
            else:
                self.setWindowTitle(self.settings.value('device_name','كاشير المطعم')+' — بروست السحابي')
                if self.settings.value('fullscreen',False,type=bool):self.showFullScreen()
                else:self.showMaximized()
        wizard.deleteLater()

    def toggle_fullscreen(self):
        if self.isFullScreen():self.showMaximized()
        else:self.showFullScreen()

    def loaded(self,ok):
        self.statusBar().showMessage('تم تحميل صفحة الكاشير' if ok else 'تعذر تحميل الكاشير. راجع الإنترنت أو افتح فحص وإصلاح.')

    def external_window(self,request):
        url=request.requestedUrl()
        if url.scheme()=='https' and url.host()=='broost-three.vercel.app':
            QDesktopServices.openUrl(url)

    def reload_page(self):
        if QMessageBox.question(self,'إعادة الاتصال','إعادة تحميل الصفحة تفقد السلة غير المحفوظة. هل تريد المتابعة؟')==QMessageBox.StandardButton.Yes:
            self.view.setUrl(self.url)


if __name__=='__main__':
    app=QApplication(sys.argv)
    apply_cloud_theme(app)
    # Match the installer's mutex so two cashiers or an in-use update cannot overlap.
    mutex=None
    if sys.platform=='win32' and '--setup-smoke' not in sys.argv:
        import ctypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateMutexW.restype=ctypes.c_void_p
        kernel.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_wchar_p]
        mutex=kernel.CreateMutexW(None,False,'Local\\BroostCloudPOS')
        if not mutex:
            QMessageBox.critical(None,'بروست','تعذر تأمين تشغيل البرنامج. أعد تشغيل Windows ثم حاول مجددًا.')
            sys.exit(1)
        if ctypes.get_last_error()==183:
            QMessageBox.information(None,'بروست','الكاشير مفتوح بالفعل. افتح نافذته من شريط المهام.')
            sys.exit(0)
    window=CloudWindow()
    icon=os.path.join(os.path.dirname(sys.executable) if getattr(sys,'frozen',False) else os.path.dirname(__file__),'logo.ico')
    window.setWindowIcon(QIcon(icon))
    window.showMaximized()
    sys.exit(app.exec())
