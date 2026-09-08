"""Native cloud cashier shell: no local order database or sync worker."""
import json
import os
import sys
import uuid

from PyQt6.QtCore import QFile, QIODevice, QObject, QSettings, QUrl, pyqtSlot
from PyQt6.QtGui import QAction, QDesktopServices, QIcon
from PyQt6.QtWidgets import QApplication, QMainWindow, QMessageBox, QInputDialog
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineScript
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel

from core.pos_defaults import load_pos_defaults
from core import config


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
        self.settings=QSettings('Broost','CloudPOS')
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
        config.SELECTED_PRINTER=self.settings.value('printer','')
        toolbar=self.addToolBar('بروست')
        printer_action=QAction('اختيار الطابعة',self)
        printer_action.triggered.connect(self.choose_printer);toolbar.addAction(printer_action)
        reload_action=QAction('إعادة الاتصال',self)
        reload_action.triggered.connect(self.reload_page);toolbar.addAction(reload_action)
        self.view.loadFinished.connect(self.loaded)
        self.view.setUrl(self.url)

    def loaded(self,ok):
        self.statusBar().showMessage('متصل بالسيرفر' if ok else 'تعذر الاتصال بالسيرفر. راجع الإنترنت واضغط إعادة الاتصال.')

    def external_window(self,request):
        url=request.requestedUrl()
        if url.scheme()=='https' and url.host()=='broost-three.vercel.app':
            QDesktopServices.openUrl(url)

    def choose_printer(self):
        from PyQt6.QtPrintSupport import QPrinterInfo
        names=[p.printerName() for p in QPrinterInfo.availablePrinters()]
        if not names:
            QMessageBox.warning(self,'الطباعة','لم يتم العثور على طابعة في Windows');return
        name,ok=QInputDialog.getItem(self,'الطابعة','اختر طابعة الفواتير',names,0,False)
        if ok:
            config.SELECTED_PRINTER=name;self.settings.setValue('printer',name)

    def reload_page(self):
        if QMessageBox.question(self,'إعادة الاتصال','إعادة تحميل الصفحة تفقد السلة غير المحفوظة. هل تريد المتابعة؟')==QMessageBox.StandardButton.Yes:
            self.view.setUrl(self.url)


if __name__=='__main__':
    app=QApplication(sys.argv)
    window=CloudWindow()
    icon=os.path.join(os.path.dirname(sys.executable) if getattr(sys,'frozen',False) else os.path.dirname(__file__),'logo.ico')
    window.setWindowIcon(QIcon(icon))
    window.showMaximized()
    sys.exit(app.exec())
