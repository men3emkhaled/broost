"""Arabic first-run setup and repeatable diagnostics for the cloud cashier."""
import base64
import json
import os
from pathlib import Path
import sys

from PyQt6.QtCore import QByteArray, QBuffer, QIODevice, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QFont
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWizard, QWizardPage)

from core import config
from core.cloud_theme import apply_cloud_theme
from core.cloud_diagnostics import (VERSION, autostart_enabled, check_connection,
    connection_fingerprint, device_checks, safe_report, set_autostart)


def apply_print_settings(settings):
    config.SELECTED_PRINTER = settings.value('printer', '')
    try:
        width = int(settings.value('paper_width', 80))
        scale = float(settings.value('font_scale', 1.0))
    except (TypeError, ValueError):
        width, scale = 80, 1.0
    config.PAPER_WIDTH = width if width in (58, 80) else 80
    config.PRINT_FONT_SCALE = scale if scale in (1.0, 1.2) else 1.0


def setup_required(settings, defaults):
    if settings.value('skip_setup_checks', False, type=bool):
        return False
    return (settings.value('setup_version', '') != VERSION or
            settings.value('connection_fingerprint', '') != connection_fingerprint(defaults))


def test_receipt():
    import qrcode
    matrix = qrcode.QRCode(border=4, box_size=1)
    matrix.add_data('BROOST-PRINT-TEST'); matrix.make(fit=True)
    cells = matrix.get_matrix()
    image = QImage(len(cells)*4, len(cells)*4, QImage.Format.Format_RGB32)
    image.fill(QColor('white'))
    for y, row in enumerate(cells):
        for x, dark in enumerate(row):
            if dark:
                for dy in range(4):
                    for dx in range(4):
                        image.setPixelColor(x*4+dx, y*4+dy, QColor('black'))
    buffer = QBuffer(); buffer.open(QIODevice.OpenModeFlag.WriteOnly); image.save(buffer, 'PNG')
    encoded = base64.b64encode(bytes(buffer.data())).decode()
    return f'''<html dir="rtl"><body style="font-family:Tahoma;text-align:center;font-size:12px">
        <h2>بروست — اختبار الطابعة</h2><p>هذه ورقة اختبار فقط — ليست فاتورة بيع</p>
        <table width="100%"><tr><th>الصنف</th><th>العدد</th><th>الإجمالي</th></tr>
        <tr><td>ربع فرخة ورك — عادي</td><td>3</td><td>405.00</td></tr></table>
        <h3>إجمالي تجريبي: 405.00 ج.م</h3><p>0123456789<br>العربية واضحة والأرقام كاملة</p>
        <img src="data:image/png;base64,{encoded}" width="116" height="116">
        <p>تأكد من وضوح النص والرمز وعدم قص أطراف الورقة.</p></body></html>'''


class ConnectionWorker(QThread):
    progress = pyqtSignal(str)
    result = pyqtSignal(dict)

    def __init__(self, defaults, pin, parent):
        super().__init__(parent)
        self.defaults, self.pin = defaults, pin

    def run(self):
        try:
            self.result.emit(check_connection(self.defaults, self.pin, self.progress.emit))
        finally:
            self.pin = ''


class CheckPage(QWizardPage):
    def __init__(self, title, subtitle):
        super().__init__()
        self.setTitle(title); self.setSubTitle(subtitle)
        self.layout_box = QVBoxLayout(self)
        self.ready = False

    def isComplete(self):
        return self.ready

    def set_ready(self, value):
        self.ready = bool(value); self.completeChanged.emit()


class SetupWizard(QWizard):
    def __init__(self, settings, defaults, settings_dir, parent=None):
        apply_cloud_theme(QApplication.instance())
        super().__init__(parent)
        self.settings, self.defaults = settings, defaults
        self.settings_dir = Path(settings_dir)
        self.connection = {}
        self.checks = []
        self.worker = None
        self.print_sent = False
        self.setWindowTitle('بروست — تجهيز جهاز المطعم وفحص التشغيل')
        self.setFont(QFont('Tahoma',11))
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setMinimumSize(720, 540)
        self.resize(820, 620)
        self.setButtonText(QWizard.WizardButton.NextButton, 'التالي')
        self.setButtonText(QWizard.WizardButton.BackButton, 'السابق')
        self.setButtonText(QWizard.WizardButton.FinishButton, 'حفظ وبدء التشغيل')
        self.setButtonText(QWizard.WizardButton.CancelButton, 'إغلاق التجهيز')
        for button in (QWizard.WizardButton.NextButton,QWizard.WizardButton.FinishButton):
            self.button(button).setObjectName('setupPrimary')
        self.setStyleSheet('''
            QWizard, QWizardPage { background:#f5f6f8; color:#20252b; font-family:Tahoma; font-size:14px; }
            QLabel, QCheckBox { color:#20252b; background:transparent; }
            QLineEdit,QComboBox { background:#ffffff; color:#20252b; padding:8px;
                border:1px solid #8996a5; border-radius:5px;
                selection-background-color:#176b46; selection-color:#ffffff; }
            QComboBox QAbstractItemView { background:#ffffff; color:#20252b;
                selection-background-color:#176b46; selection-color:#ffffff; }
            QPushButton { background:#ffffff; color:#20252b; border:1px solid #8996a5;
                border-radius:5px; padding:9px 16px; min-height:18px; }
            QPushButton:hover { background:#e8eef4; border-color:#596574; }
            QPushButton:pressed { background:#d5e0eb; }
            QPushButton:focus, QLineEdit:focus, QComboBox:focus { border:2px solid #135ca8; }
            QPushButton#setupPrimary { background:#176b46; color:#ffffff; border-color:#176b46; font-weight:bold; }
            QPushButton#setupPrimary:hover { background:#115737; }
            QPushButton#setupPrimary:pressed { background:#0b452a; }
            QPushButton#setupPrimary:focus { border:2px solid #135ca8; }
            QPushButton:disabled, QPushButton#setupPrimary:disabled { background:#e5e9ee; color:#66717f; border-color:#bdc6d0; }
            QLineEdit:disabled, QComboBox:disabled { background:#e5e9ee; color:#66717f; }
            QCheckBox:disabled { color:#66717f; }
        ''')
        self.setOption(QWizard.WizardOption.HaveCustomButton1, True)
        self.setButtonText(QWizard.WizardButton.CustomButton1, 'حفظ تقرير الفحص')
        self.setOption(QWizard.WizardOption.HaveCustomButton2, True)
        self.setButtonText(QWizard.WizardButton.CustomButton2, 'تخطي الفحص وبدء الكاشير')
        self.customButtonClicked.connect(self.handle_custom_button)
        self.build_device_page()
        self.build_connection_page()
        self.build_printer_page()
        self.build_options_page()
        self.build_summary_page()
        self.currentIdChanged.connect(self.page_changed)
        self.refresh_device()

    def text(self, page, text):
        label = QLabel(text); label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.PlainText)
        page.layout_box.addWidget(label)
        return label

    def build_device_page(self):
        self.device_page = CheckPage('١. فحص الجهاز', 'نتأكد من التوافق والصلاحيات قبل تجهيز الكاشير.')
        self.device_status = self.text(self.device_page, '')
        self.text(self.device_page, 'بيانات البيع محفوظة على السيرفر. لا يتم استيراد قواعد بيانات قديمة أو تصفير بيانات المطعم أثناء التثبيت.')
        button = QPushButton('إعادة فحص الجهاز'); button.clicked.connect(self.refresh_device)
        self.device_page.layout_box.addWidget(button)
        self.device_page.layout_box.addStretch()
        self.addPage(self.device_page)

    def refresh_device(self):
        self.checks = device_checks(self.settings_dir)
        self.device_status.setText('\n\n'.join(('✓ ' if r['ok'] else '✗ ')+r['name']+' — '+r['message'] for r in self.checks))
        self.device_page.set_ready(all(r['ok'] for r in self.checks))

    def build_connection_page(self):
        self.connection_page = CheckPage('٢. ربط المطعم', 'الفحص يتحقق من السيرفر والدخول والمنيو بدون إنشاء أي فاتورة.')
        self.text(self.connection_page, 'السيرفر: '+self.defaults['server_url'])
        self.pin = QLineEdit(); self.pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin.setPlaceholderText('رمز دخول الكاشير'); self.pin.setMaxLength(128)
        self.pin.returnPressed.connect(self.start_connection)
        self.connection_page.layout_box.addWidget(self.pin)
        self.connection_button = QPushButton('اختبار الاتصال والدخول')
        self.connection_button.clicked.connect(self.start_connection)
        self.connection_page.layout_box.addWidget(self.connection_button)
        self.connection_status = self.text(self.connection_page, 'أدخل رمز الكاشير ثم ابدأ الاختبار. الرمز لا يُحفظ على الجهاز.')
        self.connection_page.layout_box.addStretch(); self.addPage(self.connection_page)

    def start_connection(self):
        if self.worker is not None and self.worker.isRunning():
            return
        if not self.pin.text().strip():
            self.connection_status.setText('أدخل رمز الكاشير أولًا.'); return
        self.connection = {}; self.connection_page.set_ready(False)
        self.worker = ConnectionWorker(self.defaults, self.pin.text(), self)
        self.pin.clear(); self.pin.setEnabled(False); self.connection_button.setEnabled(False)
        self.button(QWizard.WizardButton.BackButton).setEnabled(False)
        self.worker.progress.connect(self.connection_status.setText)
        self.worker.result.connect(self.connection_finished)
        self.worker.finished.connect(self.connection_idle)
        self.worker.start()

    def connection_finished(self, result):
        self.connection = result
        self.connection_status.setText(result['message'])
        self.connection_page.set_ready(result['ok'])

    def connection_idle(self):
        self.pin.setEnabled(True); self.connection_button.setEnabled(True)
        self.button(QWizard.WizardButton.BackButton).setEnabled(True)

    def build_printer_page(self):
        self.printer_page = CheckPage('٣. إعداد الطابعة وتجربتها', 'وصل الطابعة وثبّت تعريفها في Windows ثم اطبع ورقة الاختبار.')
        form = QFormLayout()
        self.printers = QComboBox()
        self.paper = QComboBox(); self.paper.addItem('80 مم',80); self.paper.addItem('58 مم',58)
        self.paper.setCurrentIndex(1 if config.PAPER_WIDTH == 58 else 0)
        self.font = QComboBox(); self.font.addItem('عادي',1.0); self.font.addItem('كبير',1.2)
        self.font.setCurrentIndex(1 if getattr(config,'PRINT_FONT_SCALE',1.0) == 1.2 else 0)
        form.addRow('طابعة الفواتير والمطبخ',self.printers)
        form.addRow('عرض الورق',self.paper); form.addRow('حجم الكتابة',self.font)
        self.printer_page.layout_box.addLayout(form)
        refresh = QPushButton('تحديث قائمة الطابعات'); refresh.clicked.connect(self.refresh_printers)
        self.printer_page.layout_box.addWidget(refresh)
        self.print_button = QPushButton('طباعة ورقة اختبار'); self.print_button.clicked.connect(self.send_test_print)
        self.printer_page.layout_box.addWidget(self.print_button)
        self.print_status = self.text(self.printer_page, '')
        self.print_confirmed = QCheckBox('خرجت الورقة فعلًا، والعربية والأرقام وQR واضحين بدون قص')
        self.print_confirmed.setEnabled(False)
        self.print_confirmed.toggled.connect(self.on_print_confirmed_toggled)
        self.printer_page.layout_box.addWidget(self.print_confirmed)
        self.skip_printer = QCheckBox('تخطي إعداد الطابعة (العمل بدون طابعة على هذا الجهاز)')
        self.skip_printer.setStyleSheet('font-weight: bold; color: #176b46; padding-top: 8px;')
        self.skip_printer.toggled.connect(self.on_skip_printer_toggled)
        self.printer_page.layout_box.addWidget(self.skip_printer)
        self.printer_page.layout_box.addStretch()
        for combo in (self.printers,self.paper,self.font):
            combo.currentIndexChanged.connect(self.invalidate_print)
        self.refresh_printers(); self.addPage(self.printer_page)

    def on_print_confirmed_toggled(self, checked):
        if not (hasattr(self, 'skip_printer') and self.skip_printer.isChecked()):
            self.printer_page.set_ready(checked)

    def on_skip_printer_toggled(self, checked):
        if checked:
            self.print_confirmed.setChecked(False)
            self.print_confirmed.setEnabled(False)
            self.print_button.setEnabled(False)
            self.printers.setEnabled(False)
            self.paper.setEnabled(False)
            self.font.setEnabled(False)
            self.print_status.setText('تم اختيار العمل بدون طابعة على هذا الجهاز. يمكنك إعداد الطابعة لاحقًا في أي وقت.')
            self.printer_page.set_ready(True)
        else:
            self.printers.setEnabled(True)
            self.paper.setEnabled(True)
            self.font.setEnabled(True)
            self.invalidate_print()

    def refresh_printers(self):
        from PyQt6.QtPrintSupport import QPrinterInfo
        from core.printing import is_virtual_printer
        previous = self.printers.currentText() or self.settings.value('printer','')
        self.printers.clear()
        self.printers.addItems([p.printerName() for p in QPrinterInfo.availablePrinters() if not is_virtual_printer(p)])
        index = self.printers.findText(previous)
        if index >= 0:
            self.printers.setCurrentIndex(index)
        else:
            # Auto-detect Rongta RP350 / 80mm thermal receipt printer
            rongta_kws = ("rp350", "rp-350", "rongta", "rongeta", "rp326", "rp327", "rp330", "rp80", "80mm", "pos", "thermal", "receipt")
            for i in range(self.printers.count()):
                pname = self.printers.itemText(i).lower()
                if any(kw in pname for kw in rongta_kws):
                    self.printers.setCurrentIndex(i)
                    break
        self.invalidate_print()

    def invalidate_print(self, *args):
        if hasattr(self, 'skip_printer') and self.skip_printer.isChecked():
            self.printer_page.set_ready(True)
            return
        self.print_sent = False; self.print_confirmed.setChecked(False); self.print_confirmed.setEnabled(False)
        available = self.printers.count() > 0
        self.print_button.setEnabled(available)
        self.print_status.setText('اطبع ورقة اختبار لتأكيد هذه الإعدادات.' if available else
                                 'لم يتم العثور على طابعة فعلية. وصل الطابعة وثبّت تعريفها ثم اضغط تحديث القائمة (أو فعّل خيار تخطي الطابعة أعلاه للعمل بدون طابعة).')

    def send_test_print(self):
        from core.printing import print_text_to_printer
        old = (config.SELECTED_PRINTER,config.PAPER_WIDTH,getattr(config,'PRINT_FONT_SCALE',1.0))
        config.SELECTED_PRINTER = self.printers.currentText()
        config.PAPER_WIDTH, config.PRINT_FONT_SCALE = self.paper.currentData(),self.font.currentData()
        self.print_button.setEnabled(False)
        try:
            self.print_sent = bool(print_text_to_printer(test_receipt(),self))
        except Exception:
            self.print_sent = False
        finally:
            config.SELECTED_PRINTER,config.PAPER_WIDTH,config.PRINT_FONT_SCALE = old
            self.print_button.setEnabled(True)
        self.print_confirmed.setChecked(False); self.print_confirmed.setEnabled(self.print_sent)
        self.print_status.setText('تم إرسال الورقة للطابعة. تأكد من خروجها ووضوحها ثم علّم التأكيد.' if self.print_sent
                                 else 'لم تنجح الطباعة. راجع توصيل الطابعة وتعريفها وحالتها ثم أعد الاختبار.')

    def build_options_page(self):
        page = CheckPage('٤. إعداد التشغيل', 'إعدادات هذا الجهاز فقط؛ يمكنك تعديلها لاحقًا من فحص وإصلاح.')
        form = QFormLayout()
        self.device_name = QLineEdit(self.settings.value('device_name','كاشير المطعم'))
        self.device_name.setMaxLength(60); form.addRow('اسم الجهاز',self.device_name)
        page.layout_box.addLayout(form)
        self.autostart = QCheckBox('فتح الكاشير تلقائيًا عند الدخول إلى Windows')
        self.autostart.setChecked(autostart_enabled())
        self.autostart.setEnabled(bool(getattr(sys,'frozen',False)))
        self.fullscreen = QCheckBox('تشغيل بملء الشاشة')
        self.fullscreen.setChecked(self.settings.value('fullscreen',False,type=bool))
        page.layout_box.addWidget(self.autostart); page.layout_box.addWidget(self.fullscreen)
        self.text(page, 'للخروج من ملء الشاشة اضغط F11. لا يتم تغيير إعدادات الطاقة أو الشبكة في Windows.')
        page.layout_box.addStretch(); page.set_ready(True); self.addPage(page)

    def build_summary_page(self):
        self.summary_page = CheckPage('٥. نتيجة التجهيز', 'نبدأ التشغيل بعد نجاح الفحوص وتأكيد الطباعة الفعلية.')
        self.summary = self.text(self.summary_page,'')
        self.summary_page.layout_box.addStretch(); self.addPage(self.summary_page)

    def page_changed(self, page_id):
        if self.currentPage() is self.summary_page:
            printer_ok = self.print_confirmed.isChecked() or (hasattr(self, 'skip_printer') and self.skip_printer.isChecked())
            ready = self.device_page.isComplete() and self.connection_page.isComplete() and printer_ok
            self.summary_page.set_ready(ready)
            if hasattr(self, 'skip_printer') and self.skip_printer.isChecked():
                printer_status = '✓ تم تخطي إعداد الطابعة (العمل بدون طابعة)'
                printer_info_str = 'بدون طابعة'
            elif self.print_confirmed.isChecked():
                printer_status = '✓ تم تأكيد الطباعة الفعلية'
                printer_info_str = self.printers.currentText()+f' — {self.paper.currentData()} مم'
            else:
                printer_status = 'لم يتم تأكيد الطباعة'
                printer_info_str = self.printers.currentText()+f' — {self.paper.currentData()} مم'

            self.summary.setText(('✓ جاهز للتشغيل\n\n' if ready else 'التجهيز غير مكتمل\n\n')+
                self.connection.get('message','لم يُختبر الاتصال')+'\n\n'+
                printer_status+
                '\n\nاسم الجهاز: '+self.device_name.text().strip()+
                '\nالطابعة: '+printer_info_str+
                '\n\nلا توجد فاتورة تجريبية أو تغيير في ترقيم الطلبات. سجّل دخول الكاشير لبدء العمل.')

    def handle_custom_button(self, which):
        if which == QWizard.WizardButton.CustomButton1:
            self.export_report()
        elif which == QWizard.WizardButton.CustomButton2:
            self.skip_and_start()

    def skip_and_start(self):
        reply = QMessageBox.question(
            self,
            'تخطي الفحص والتشغيل',
            'هل تريد تخطي معالج الفحص وتشغيل الكاشير مباشرة؟\n\n'
            'لن يطلب النظام الفحص مجددًا عند التشغيل، ويمكنك تشغيل الفحص في أي وقت من شريط الأدوات.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.save_minimal_settings_and_accept()

    def save_minimal_settings_and_accept(self):
        try:
            device_name = self.device_name.text().strip() if hasattr(self, 'device_name') and self.device_name.text().strip() else self.settings.value('device_name', 'كاشير المطعم')
            values = {
                'printer': self.settings.value('printer', ''),
                'device_name': device_name,
                'fullscreen': self.fullscreen.isChecked() if hasattr(self, 'fullscreen') else self.settings.value('fullscreen', False, type=bool),
                'connection_fingerprint': connection_fingerprint(self.defaults),
                'setup_version': VERSION,
                'skip_setup_checks': True,
                'skip_printer': True,
            }
            for key, value in values.items():
                self.settings.setValue(key, value)
            self.settings.sync()
            if self.settings.status() != self.settings.Status.NoError:
                raise OSError('settings')
        except OSError:
            QMessageBox.warning(self, 'حفظ الإعدادات', 'تعذر حفظ إعدادات التشغيل.')
            return
        apply_print_settings(self.settings)
        super().accept()

    def export_report(self):
        path,_ = QFileDialog.getSaveFileName(self,'حفظ تقرير الفحص','Broost-diagnostics.json','JSON (*.json)')
        if path:
            try:
                Path(path).write_text(json.dumps(safe_report(self.checks,self.connection,
                    self.print_confirmed.isChecked(),self.paper.currentData()),ensure_ascii=False,indent=2),encoding='utf-8')
            except OSError:
                QMessageBox.warning(self,'التقرير','تعذر حفظ التقرير في هذا المكان. اختر مجلدًا آخر.')

    def accept(self):
        printer_ok = (self.print_sent and self.print_confirmed.isChecked()) or (hasattr(self, 'skip_printer') and self.skip_printer.isChecked())
        if not (self.device_page.isComplete() and self.connection_page.isComplete() and printer_ok):
            return
        if not self.device_name.text().strip():
            QMessageBox.warning(self,'اسم الجهاز','أدخل اسمًا للجهاز في صفحة إعداد التشغيل.'); return
        try:
            if getattr(sys,'frozen',False):
                set_autostart(self.autostart.isChecked())
            is_skipped = hasattr(self, 'skip_printer') and self.skip_printer.isChecked()
            printer_val = '' if is_skipped else self.printers.currentText()
            values = {'printer':printer_val,'paper_width':self.paper.currentData(),
                      'font_scale':self.font.currentData(),'device_name':self.device_name.text().strip(),
                      'fullscreen':self.fullscreen.isChecked(),
                      'connection_fingerprint':connection_fingerprint(self.defaults),'setup_version':VERSION,
                      'skip_printer':is_skipped}
            for key,value in values.items():
                self.settings.setValue(key,value)
            self.settings.sync()
            if self.settings.status() != self.settings.Status.NoError:
                raise OSError('settings')
        except OSError:
            QMessageBox.warning(self,'حفظ الإعدادات','تعذر حفظ إعدادات التشغيل. راجع صلاحيات المستخدم ثم أعد المحاولة.'); return
        apply_print_settings(self.settings)
        super().accept()

    def reject(self):
        if self.worker is not None and self.worker.isRunning():
            self.connection_status.setText('انتظر انتهاء فحص الاتصال قبل الإغلاق؛ مهلة كل طلب 10 ثوانٍ.'); return
        super().reject()

    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            event.ignore(); self.reject()
        else:
            super().closeEvent(event)
