# -*- coding: utf-8 -*-
"""Broost POS - Sales Reports & Analytics Dashboard"""
from datetime import datetime, timedelta
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QFrame, QWidget,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QProgressBar, QTextEdit, QComboBox, QDateEdit,
    QAbstractItemView, QSizePolicy
)
import database
from core.display_text import pos_text
from styles import STYLE_SHEET
from dialogs.receipt import ReceiptSimDialog
from dialogs.login import PasswordVerificationDialog


class ReportPrintDialog(QDialog):
    """Simple thermal printer preview and print dialog for business reports."""
    def __init__(self, title_text, report_text, parent=None):
        super().__init__(parent)
        self.setWindowTitle("معاينة تقرير المبيعات")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setFixedSize(380, 520)
        self.setStyleSheet(STYLE_SHEET)
        
        self.report_text = report_text
        self.title_text = title_text
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        
        title = QLabel(self.title_text, self)
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #0078d4;")
        layout.addWidget(title)
        
        self.txt_preview = QTextEdit(self)
        self.txt_preview.setReadOnly(True)
        self.txt_preview.setText(self.report_text)
        self.txt_preview.setStyleSheet("background: white; color: black; font-family: 'Courier New', monospace; font-size: 11px; border: 1px solid #e5e7eb; border-radius: 6px; padding: 10px;")
        layout.addWidget(self.txt_preview)
        
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        self.btn_hard_print = QPushButton("طباعة ورقية", self)
        self.btn_hard_print.setStyleSheet("QPushButton { background-color: #0078d4; color: white; border: none; border-radius: 6px; font-weight: bold; font-size: 12px; } QPushButton:hover { background-color: #106ebe; }")
        self.btn_hard_print.clicked.connect(self.trigger_hard_print)
        
        btn_done = QPushButton("إغلاق", self)
        btn_done.setObjectName("BtnDark")
        btn_done.clicked.connect(self.accept)
        
        btn_layout.addWidget(btn_done)
        btn_layout.addWidget(self.btn_hard_print)
        layout.addLayout(btn_layout)
        
    def trigger_hard_print(self):
        from core import config
        from core.printing import print_text_to_printer
        if not config.PRINTER_ONLINE:
            QMessageBox.critical(self, "خطأ بالطابعة", "تنبيه: تعذر إرسال الأمر! طابعة الفواتير غير متصلة أو انقطع اتصال الكابل.")
            return
            
        success = print_text_to_printer(self.report_text, self)
        if success:
            QMessageBox.information(self, "طابعة النظام", "تم إرسال التقرير للمطبوعة بنجاح.")


class ReportsDialog(QDialog):
    """Business Analytics and Graphical Reports Dashboard with detailed order history."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("لوحة تقارير المبيعات")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        
        # Screen resolution check
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        screen_size = screen.size() if screen else None
        self.is_small_screen = bool(
            screen_size and (screen_size.width() <= 1366 or screen_size.height() <= 768)
        )
        available = screen.availableGeometry() if screen else None
        if available:
            self.resize(
                min(1120, max(960, available.width() - 70)),
                min(720, max(620, available.height() - 70)),
            )
        else:
            self.resize(1060, 680)
        self.setMinimumSize(940, 600)
            
        self.setStyleSheet(STYLE_SHEET + """
            QDialog { background: #f7f7f8; }
            QTabWidget::pane {
                background: #ffffff; border: 1px solid #e4e4e7;
                border-radius: 12px; top: -1px;
            }
            QTabBar::tab {
                min-width: 170px; min-height: 38px; padding: 0 16px;
                background: #f4f4f5; color: #52525b;
                border: 1px solid #e4e4e7; border-bottom: none;
                font-size: 12px; font-weight: 700;
            }
            QTabBar::tab:selected {
                background: #ffffff; color: #be123c;
                border-top: 2px solid #be123c;
            }
            QTableWidget {
                background: #ffffff; alternate-background-color: #fafafa;
                border: 1px solid #e4e4e7; border-radius: 10px;
                gridline-color: #ececef; color: #27272a;
            }
            QTableWidget::item { padding: 7px; }
            QHeaderView::section {
                background: #f4f4f5; color: #3f3f46; border: none;
                border-bottom: 1px solid #dedee3; padding: 8px 6px;
                font-size: 11px; font-weight: 800;
            }
        """)
        
        self.filter_range = "day"
        self.custom_range_start = None
        self.custom_range_end = None
        self.init_ui()
        self.update_shift_info_bar("day")
        self.load_analytics()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(11)
        
        # ── Header row ──
        header = QHBoxLayout()
        title = QLabel("لوحة المبيعات والتقارير", self)
        title.setStyleSheet("font-size: 20px; font-weight: 900; color: #18181b; border: none;")
        header.addWidget(title)
        
        header.addStretch()
        
        # Quick date filters
        self.btn_day = QPushButton("اليوم", self)
        self.btn_day.setCheckable(True)
        self.btn_day.setChecked(True)
        self.btn_day.setFixedSize(82, 36)
        self.btn_day.clicked.connect(lambda: self.change_filter("day"))
        
        self.btn_week = QPushButton("7 أيام", self)
        self.btn_week.setCheckable(True)
        self.btn_week.setFixedSize(82, 36)
        self.btn_week.clicked.connect(lambda: self.change_filter("week"))
        
        self.btn_month = QPushButton("30 يوم", self)
        self.btn_month.setCheckable(True)
        self.btn_month.setFixedSize(82, 36)
        self.btn_month.clicked.connect(lambda: self.change_filter("month"))
        
        self.btn_all = QPushButton("كل المدة", self)
        self.btn_all.setCheckable(True)
        self.btn_all.setFixedSize(88, 36)
        self.btn_all.clicked.connect(lambda: self.change_filter("all_time"))

        # Any specific calendar day, without a retention limit.
        self.date_picker = QDateEdit(self)
        self.date_picker.setCalendarPopup(True)
        self.date_picker.setDisplayFormat("dd/MM/yyyy")
        self.date_picker.setDate(QDate.currentDate())
        self.date_picker.setMaximumDate(QDate.currentDate())
        self.date_picker.setMinimumDate(QDate(2000, 1, 1))
        self.date_picker.setFixedSize(125, 36)
        self.date_picker.dateChanged.connect(lambda: self.change_filter("custom_date"))

        # Every month present in the database remains directly selectable.
        self.month_picker = QComboBox(self)
        self.month_picker.setFixedSize(135, 36)
        self.month_picker.addItem("اختار شهر...", None)
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("""
            SELECT DISTINCT substr(created_at, 1, 7)
            FROM orders
            WHERE created_at IS NOT NULL
            ORDER BY 1 DESC
        """)
        for (year_month,) in c.fetchall():
            if year_month and len(year_month) == 7:
                self.month_picker.addItem(year_month, year_month)
        conn.close()
        self.month_picker.currentIndexChanged.connect(self._on_month_picked)

        self.btn_custom_range = QPushButton("من فترة لفترة", self)
        self.btn_custom_range.setFixedSize(125, 36)
        self.btn_custom_range.clicked.connect(self.open_custom_range_dialog)
        
        # Print Summary Report button
        self.btn_print_summary = QPushButton("طباعة التقرير", self)
        self.btn_print_summary.setFixedSize(126, 36)
        self.btn_print_summary.setStyleSheet("""
            QPushButton {
                background-color: #107c10;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #0b5a0b;
            }
        """)
        self.btn_print_summary.clicked.connect(self.print_summary_report)
        
        # Dynamic Cashier Filter dropdown
        self.cb_cashier = QComboBox(self)
        self.cb_cashier.setFixedSize(165, 36)
        self.cb_cashier.setStyleSheet("""
            QComboBox {
                background-color: #ffffff;
                color: #1a1a1a;
                border: 1px solid #d1d5db;
                border-radius: 6px;
                padding: 4px 10px;
                font-weight: bold;
                font-size: 12px;
            }
        """)
        # Load cashier names dynamically
        c1_name = ""
        try:
            conn = database.get_connection()
            c = conn.cursor()
            c.execute("SELECT value FROM settings WHERE key='cashier_1_name'")
            r1 = c.fetchone()
            c1_name = r1[0] if r1 else ""
            conn.close()
        except Exception:
            pass

        self.cb_cashier.addItem("كل الورديات", "all")
        if c1_name:
            self.cb_cashier.addItem(c1_name, c1_name)
            
        self.cb_cashier.currentIndexChanged.connect(lambda: self.load_analytics())
        
        header.addWidget(self.cb_cashier)
        header.addWidget(self.btn_print_summary)
        
        # Close button
        btn_x = QPushButton("✕", self)
        btn_x.setFixedSize(36, 36)
        btn_x.setStyleSheet("QPushButton { background: #f3f4f6; color: #4b5563; border: 1px solid #e5e7eb; border-radius: 6px; font-weight: bold; font-size: 14px; padding: 0; } QPushButton:hover { background: #fee2e2; color: #dc2626; border-color: #fca5a5; }")
        btn_x.clicked.connect(self.accept)
        header.addWidget(btn_x)
        
        layout.addLayout(header)

        filters_frame = QFrame(self)
        filters_frame.setObjectName("ReportFilters")
        filters_frame.setStyleSheet(
            "QFrame#ReportFilters { background:#ffffff; border:1px solid #e4e4e7; "
            "border-radius:10px; } QFrame#ReportFilters QLabel { border:none; background:transparent; "
            "color:#52525b; font-weight:700; }"
        )
        filter_row = QHBoxLayout(filters_frame)
        filter_row.setContentsMargins(10, 8, 10, 8)
        filter_row.setSpacing(7)
        filter_row.addWidget(self.btn_day)
        filter_row.addWidget(self.btn_week)
        filter_row.addWidget(self.btn_month)
        filter_row.addWidget(self.btn_all)
        filter_row.addSpacing(8)
        filter_row.addWidget(QLabel("يوم:", self))
        filter_row.addWidget(self.date_picker)
        filter_row.addWidget(QLabel("شهر:", self))
        filter_row.addWidget(self.month_picker)
        filter_row.addWidget(self.btn_custom_range)
        filter_row.addStretch()
        layout.addWidget(filters_frame)

        # ── Shift / Business Day Info Bar (visible only on "day" filter) ──
        self.shift_info_bar = QFrame(self)
        self.shift_info_bar.setObjectName("ShiftInfoBar")
        self.shift_info_bar.setStyleSheet("""
            QFrame#ShiftInfoBar {
                background: #eff6ff;
                border: 1px solid #bfdbfe;
                border-radius: 8px;
                padding: 0px;
            }
        """)
        shift_bar_lyt = QHBoxLayout(self.shift_info_bar)
        shift_bar_lyt.setContentsMargins(14, 7, 14, 7)
        shift_bar_lyt.setSpacing(8)

        self.lbl_shift_period = QLabel("", self.shift_info_bar)
        self.lbl_shift_period.setStyleSheet(
            "font-size: 12px; font-weight: bold; color: #1d4ed8; "
            "border: none; background: transparent;"
        )
        shift_bar_lyt.addWidget(self.lbl_shift_period)
        shift_bar_lyt.addStretch()

        self.lbl_shift_status = QLabel("", self.shift_info_bar)
        self.lbl_shift_status.setStyleSheet(
            "font-size: 11px; font-weight: bold; "
            "border: none; background: transparent;"
        )
        shift_bar_lyt.addWidget(self.lbl_shift_status)

        self.shift_info_bar.setVisible(False)  # Hidden by default
        layout.addWidget(self.shift_info_bar)

        # ── Tab widget ──
        self.tabs = QTabWidget(self)
        
        # ── Tab 1: Overview ──
        tab_overview = QWidget()
        overview_layout = QVBoxLayout(tab_overview)
        overview_layout.setContentsMargins(14, 14, 14, 14)
        overview_layout.setSpacing(12)
        
        # Metrics Grid
        metrics_grid = QGridLayout()
        metrics_grid.setSpacing(10)
        
        self.card_sales = self.create_stat_card("صافي الإيرادات", "0.00 ج.م", "#0369a1")
        self.card_orders = self.create_stat_card("الفواتير المكتملة", "0", "#15803d")
        self.card_dish = self.create_stat_card("الأكثر طلبًا", "لا يوجد", "#b45309")
        self.card_hour = self.create_stat_card("ساعة الذروة", "8:00 مساءً", "#be123c")
        
        metrics_grid.addWidget(self.card_sales, 0, 0)
        metrics_grid.addWidget(self.card_orders, 0, 1)
        metrics_grid.addWidget(self.card_dish, 0, 2)
        metrics_grid.addWidget(self.card_hour, 0, 3)
        for column in range(4):
            metrics_grid.setColumnStretch(column, 1)
        overview_layout.addLayout(metrics_grid)
        
        # Distribution charts and leaderboard row
        charts_layout = QHBoxLayout()
        charts_layout.setSpacing(14)
        
        # Channels comparison box
        self.chan_box = QFrame(tab_overview)
        self.chan_box.setMinimumHeight(210)
        self.chan_box.setStyleSheet("background: #ffffff; border: 1px solid #e4e4e7; border-radius: 10px;")
        chan_layout = QVBoxLayout(self.chan_box)
        chan_layout.setContentsMargins(16, 14, 16, 14)
        chan_title = QLabel("المبيعات حسب قناة الطلب", self.chan_box)
        chan_title.setStyleSheet("font-weight: 900; color: #27272a; font-size: 13px; border: none; background: transparent;")
        chan_layout.addWidget(chan_title)
        
        self.bars_container = QWidget(self.chan_box)
        self.bars_layout = QVBoxLayout(self.bars_container)
        self.bars_layout.setContentsMargins(0, 8, 0, 0)
        self.bars_layout.setSpacing(12)
        chan_layout.addWidget(self.bars_container)
        charts_layout.addWidget(self.chan_box, stretch=1)
        
        # Drivers leaderboard
        self.lead_box = QFrame(tab_overview)
        self.lead_box.setMinimumHeight(210)
        self.lead_box.setStyleSheet("background: #ffffff; border: 1px solid #e4e4e7; border-radius: 10px;")
        lead_layout = QVBoxLayout(self.lead_box)
        lead_layout.setContentsMargins(16, 14, 16, 14)
        lead_title = QLabel("أداء طيارين الدليفري", self.lead_box)
        lead_title.setStyleSheet("font-weight: 900; color: #27272a; font-size: 13px; border: none; background: transparent;")
        lead_layout.addWidget(lead_title)
        
        self.leaderboard_table = QTableWidget(self.lead_box)
        self.leaderboard_table.setColumnCount(3)
        self.leaderboard_table.setHorizontalHeaderLabels(["الطيار", "عدد الطلبات", "إجمالي المبيعات"])
        self.leaderboard_table.setStyleSheet("""
            QTableWidget { background: #ffffff; border: 1px solid #eeeeef; border-radius: 8px; }
            QHeaderView::section {
                background-color: #f4f4f5; color: #3f3f46;
                padding: 7px 6px; font-size: 11px; font-weight: 800;
                border: none;
                border-bottom: 1px solid #dedee3;
            }
            QTableWidget::item { padding: 7px 8px; }
        """)
        self.leaderboard_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.leaderboard_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.leaderboard_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.leaderboard_table.setColumnWidth(1, 110)
        self.leaderboard_table.setColumnWidth(2, 140)
        self.leaderboard_table.verticalHeader().setVisible(False)
        self.leaderboard_table.verticalHeader().setDefaultSectionSize(38)
        self.leaderboard_table.horizontalHeader().setFixedHeight(36)
        self.leaderboard_table.setWordWrap(False)
        self.leaderboard_table.setAlternatingRowColors(True)
        self.leaderboard_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.leaderboard_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        lead_layout.addWidget(self.leaderboard_table)
        charts_layout.addWidget(self.lead_box, stretch=2)

        
        overview_layout.addLayout(charts_layout, 1)
        self.tabs.addTab(tab_overview, "نظرة عامة وإحصائيات")
        
        # ── Tab 2: Detailed Order History ──
        tab_history = QWidget()
        history_layout = QVBoxLayout(tab_history)
        history_layout.setContentsMargins(10, 10, 10, 10)
        history_layout.setSpacing(10)
        
        # Search filter bar
        search_bar = QHBoxLayout()
        search_lbl = QLabel("بحث في السجل", tab_history)
        search_lbl.setStyleSheet("font-weight: bold; color: #1a1a1a;")
        search_bar.addWidget(search_lbl)
        
        self.search_input = QLineEdit(tab_history)
        self.search_input.setPlaceholderText("رقم الأوردر، تليفون العميل، أو اسم الطيار...")
        self.search_input.setFixedHeight(38)
        self.search_input.textChanged.connect(self.search_history)
        search_bar.addWidget(self.search_input)
        
        self.btn_delete_all = QPushButton("مسح جميع الفواتير", tab_history)
        self.btn_delete_all.setFixedHeight(38)
        self.btn_delete_all.setStyleSheet("""
            QPushButton {
                background: #fde7e9;
                color: #a80000;
                border: 1px solid #fbc4c4;
                border-radius: 6px;
                font-weight: bold;
                font-size: 11px;
                padding: 0 12px;
            }
            QPushButton:hover {
                background: #e81123;
                color: white;
                border-color: #e81123;
            }
        """)
        self.btn_delete_all.clicked.connect(self.delete_all_invoices_action)
        search_bar.addWidget(self.btn_delete_all)
        
        history_layout.addLayout(search_bar)
        
        # History table
        self.history_table = QTableWidget(tab_history)
        self.history_table.setColumnCount(7)
        self.history_table.setHorizontalHeaderLabels(["الفاتورة", "التاريخ والوقت", "القناة", "طريقة الدفع", "الإجمالي", "الحالة", "إجراء"])
        header = self.history_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self.history_table.setColumnWidth(0, 75)
        self.history_table.setColumnWidth(1, 145)
        self.history_table.setColumnWidth(2, 90)
        self.history_table.setColumnWidth(3, 110)
        self.history_table.setColumnWidth(4, 95)
        self.history_table.setColumnWidth(5, 85)
        header.setFixedHeight(40)
        self.history_table.verticalHeader().setDefaultSectionSize(48)
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        history_layout.addWidget(self.history_table)
        
        self.tabs.addTab(tab_history, "سجل الفواتير والطلبات")
        layout.addWidget(self.tabs)

    def create_stat_card(self, title_txt, val_txt, val_color):
        card = QFrame(self)
        card.setMinimumHeight(108)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        card.setStyleSheet("background-color: #ffffff; border: 1px solid #e4e4e7; border-radius: 10px;")
        lyt = QVBoxLayout(card)
        lyt.setContentsMargins(16, 14, 16, 14)
        lyt.setSpacing(8)
        
        lbl_t = QLabel(title_txt, card)
        lbl_t.setStyleSheet("color: #71717a; font-size: 11px; font-weight: 700; border: none; background: transparent;")
        lbl_t.setWordWrap(True)
        lyt.addWidget(lbl_t)
        
        lbl_v = QLabel(val_txt, card)
        lbl_v.setStyleSheet(f"font-size: 16px; font-weight: 900; color: {val_color}; border: none; background: transparent;")
        lbl_v.setWordWrap(True)
        lbl_v.setMinimumHeight(32)
        lbl_v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lyt.addWidget(lbl_v)
        
        card.setProperty("label_widget", lbl_v)
        return card

    def change_filter(self, new_range):
        self.filter_range = new_range
        self.btn_day.setChecked(new_range == "day")
        self.btn_week.setChecked(new_range == "week")
        self.btn_month.setChecked(new_range == "month")
        self.btn_all.setChecked(new_range == "all_time")

        self.update_shift_info_bar(new_range)
        self.load_analytics()

    def _on_month_picked(self, index):
        if index > 0:
            self.change_filter("custom_month")

    def open_custom_range_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("اختيار فترة التقرير")
        dlg.setFixedSize(360, 190)
        dlg.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        dlg.setStyleSheet(STYLE_SHEET)

        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("حدد تاريخ البداية والنهاية:", dlg))

        dates_row = QHBoxLayout()
        start_edit = QDateEdit(dlg)
        start_edit.setCalendarPopup(True)
        start_edit.setDisplayFormat("dd/MM/yyyy")
        start_edit.setDate(
            QDate(self.custom_range_start.year, self.custom_range_start.month, self.custom_range_start.day)
            if self.custom_range_start else QDate.currentDate().addMonths(-1)
        )
        end_edit = QDateEdit(dlg)
        end_edit.setCalendarPopup(True)
        end_edit.setDisplayFormat("dd/MM/yyyy")
        end_edit.setDate(
            QDate(self.custom_range_end.year, self.custom_range_end.month, self.custom_range_end.day)
            if self.custom_range_end else QDate.currentDate()
        )
        dates_row.addWidget(QLabel("من:", dlg))
        dates_row.addWidget(start_edit)
        dates_row.addWidget(QLabel("إلى:", dlg))
        dates_row.addWidget(end_edit)
        layout.addLayout(dates_row)

        buttons = QHBoxLayout()
        btn_cancel = QPushButton("إلغاء", dlg)
        btn_cancel.clicked.connect(dlg.reject)
        btn_apply = QPushButton("عرض الفترة", dlg)
        btn_apply.clicked.connect(dlg.accept)
        buttons.addWidget(btn_cancel)
        buttons.addWidget(btn_apply)
        layout.addLayout(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        start_date = start_edit.date().toPyDate()
        end_date = end_edit.date().toPyDate()
        if start_date > end_date:
            QMessageBox.warning(self, "فترة غير صحيحة", "تاريخ البداية يجب أن يسبق تاريخ النهاية.")
            return
        self.custom_range_start = start_date
        self.custom_range_end = end_date
        self.change_filter("custom_range")

    def get_selected_period(self):
        """Return title, description, start and end for the active report filter."""
        now = datetime.now()
        if self.filter_range == "day":
            start_date = database.get_business_day_start()
            return "اليومي", f"من {start_date.strftime('%I:%M %p')} حتى الآن", start_date, now
        if self.filter_range == "week":
            return "الأسبوعي", "آخر 7 أيام", now - timedelta(days=7), now
        if self.filter_range == "month":
            return "30 يوم", "آخر 30 يومًا", now - timedelta(days=30), now
        if self.filter_range == "custom_date":
            d = self.date_picker.date().toPyDate()
            start_date = datetime(d.year, d.month, d.day)
            return "يوم محدد", d.isoformat(), start_date, start_date.replace(hour=23, minute=59, second=59)
        if self.filter_range == "custom_month":
            year_month = self.month_picker.currentData()
            if year_month:
                year, month = map(int, year_month.split("-"))
                start_date = datetime(year, month, 1)
                if month == 12:
                    next_month = datetime(year + 1, 1, 1)
                else:
                    next_month = datetime(year, month + 1, 1)
                return "شهر محدد", year_month, start_date, next_month - timedelta(seconds=1)
        if self.filter_range == "custom_range" and self.custom_range_start and self.custom_range_end:
            start_date = datetime.combine(self.custom_range_start, datetime.min.time())
            end_date = datetime.combine(self.custom_range_end, datetime.max.time()).replace(microsecond=0)
            desc = f"من {self.custom_range_start.isoformat()} إلى {self.custom_range_end.isoformat()}"
            return "فترة مخصصة", desc, start_date, end_date
        if self.filter_range == "all_time":
            conn = database.get_connection()
            c = conn.cursor()
            c.execute("SELECT MIN(created_at), MAX(created_at) FROM orders")
            first_date, last_date = c.fetchone()
            conn.close()
            if first_date and last_date:
                start_date = datetime.strptime(first_date[:19], "%Y-%m-%d %H:%M:%S")
                end_date = datetime.strptime(last_date[:19], "%Y-%m-%d %H:%M:%S")
                return "كل المدة", f"من {start_date.date()} إلى {end_date.date()}", start_date, end_date
            return "كل المدة", "لا توجد فواتير", now, now
        return "30 يوم", "آخر 30 يومًا", now - timedelta(days=30), now

    def update_shift_info_bar(self, filter_range=None):
        """Show/hide and populate the shift period info bar."""
        if filter_range is None:
            filter_range = self.filter_range

        if filter_range != "day":
            self.shift_info_bar.setVisible(False)
            return

        from datetime import datetime
        now = datetime.now()
        business_start = database.get_business_day_start()

        # Format times in readable Arabic 12-hr format
        ar_time_fmt = "%I:%M %p"
        def fmt(dt):
            s = dt.strftime(ar_time_fmt)
            s = s.replace("AM", "صباحاً").replace("PM", "مساءاً")
            return s

        start_str = fmt(business_start)
        now_str = fmt(now)

        # Calculate duration
        delta = now - business_start
        total_mins = int(delta.total_seconds() / 60)
        hours = total_mins // 60
        mins = total_mins % 60
        duration_str = f"{hours} ساعة {mins} دقيقة" if hours else f"{mins} دقيقة"

        # Check if current shift is still open
        try:
            conn = database.get_connection()
            c = conn.cursor()
            c.execute("SELECT id, opened_at FROM shifts WHERE closed_at IS NULL ORDER BY id DESC LIMIT 1")
            open_shift = c.fetchone()
            conn.close()
        except Exception:
            open_shift = None

        if open_shift:
            shift_opened = datetime.strptime(open_shift[1][:19], "%Y-%m-%d %H:%M:%S")
            self.lbl_shift_period.setText(
                f"الوردية الحالية: بدأت الساعة {fmt(shift_opened)}  →  تمشي حالياً ({duration_str})"
            )
            self.lbl_shift_status.setText("⚫︎ مفتوحة")
            self.lbl_shift_status.setStyleSheet(
                "font-size: 11px; font-weight: bold; color: #15803d; "
                "border: none; background: transparent;"
            )
        else:
            self.lbl_shift_period.setText(
                f"تقرير اليوم: من {start_str}  →  {now_str}  (مدة: {duration_str})"
            )
            self.lbl_shift_status.setText("⚪︎ وردية مغلقة")
            self.lbl_shift_status.setStyleSheet(
                "font-size: 11px; font-weight: bold; color: #b45309; "
                "border: none; background: transparent;"
            )

        self.shift_info_bar.setVisible(True)

    def search_history(self):
        self.load_analytics()

    def load_analytics(self):
        _, _, start_date, end_date = self.get_selected_period()
            
        start_str = start_date.strftime("%Y-%m-%d %H:%M:%S")
        end_str = end_date.strftime("%Y-%m-%d %H:%M:%S")
        
        # Read the current cashier filter value
        cashier_filter = self.cb_cashier.itemData(self.cb_cashier.currentIndex()) if hasattr(self, 'cb_cashier') else "all"
        
        conn = database.get_connection()
        c = conn.cursor()
        
        # 1. Total count & sales
        if cashier_filter == "all":
            c.execute("SELECT COUNT(*), SUM(o.total - COALESCE(o.delivery_fee, 0)) FROM orders o WHERE o.status='COMPLETED' AND o.created_at BETWEEN ? AND ?", (start_str, end_str))
        else:
            c.execute("""
                SELECT COUNT(*), SUM(o.total - COALESCE(o.delivery_fee, 0))
                FROM orders o 
                JOIN shifts s ON o.shift_id = s.id 
                WHERE o.status='COMPLETED' AND o.created_at BETWEEN ? AND ? AND s.cashier_name = ?
            """, (start_str, end_str, cashier_filter))
            
        o_cnt, total_sales = c.fetchone()
        total_sales = total_sales if total_sales else 0.0
        
        self.card_sales.property("label_widget").setText(f"{total_sales:,.2f} ج.م")
        self.card_orders.property("label_widget").setText(str(o_cnt))
        
        # 2. Most popular dish
        if cashier_filter == "all":
            c.execute("""
                SELECT COALESCE(oi.item_name, m.name), SUM(oi.quantity) as q
                FROM order_items oi
                LEFT JOIN menu_items m ON oi.menu_item_id = m.id
                JOIN orders o ON oi.order_id = o.id
                WHERE o.status='COMPLETED' AND o.created_at BETWEEN ? AND ?
                GROUP BY oi.menu_item_id
                ORDER BY q DESC LIMIT 1
            """, (start_str, end_str))
        else:
            c.execute("""
                SELECT COALESCE(oi.item_name, m.name), SUM(oi.quantity) as q
                FROM order_items oi
                LEFT JOIN menu_items m ON oi.menu_item_id = m.id
                JOIN orders o ON oi.order_id = o.id
                JOIN shifts s ON o.shift_id = s.id
                WHERE o.status='COMPLETED' AND o.created_at BETWEEN ? AND ? AND s.cashier_name = ?
                GROUP BY oi.menu_item_id
                ORDER BY q DESC LIMIT 1
            """, (start_str, end_str, cashier_filter))
            
        best_dish = c.fetchone()
        best_dish_txt = pos_text(best_dish[0]) if best_dish else "لا يوجد"
        self.card_dish.property("label_widget").setText(best_dish_txt)
        
        # 3. Peak hour
        if cashier_filter == "all":
            c.execute("""
                SELECT strftime('%H', o.created_at) as hr, COUNT(*) as c
                FROM orders o
                WHERE o.status='COMPLETED' AND o.created_at BETWEEN ? AND ?
                GROUP BY hr
                ORDER BY c DESC LIMIT 1
            """, (start_str, end_str))
        else:
            c.execute("""
                SELECT strftime('%H', o.created_at) as hr, COUNT(*) as c
                FROM orders o
                JOIN shifts s ON o.shift_id = s.id
                WHERE o.status='COMPLETED' AND o.created_at BETWEEN ? AND ? AND s.cashier_name = ?
                GROUP BY hr
                ORDER BY c DESC LIMIT 1
            """, (start_str, end_str, cashier_filter))
            
        peak_hour = c.fetchone()
        if peak_hour:
            h = int(peak_hour[0])
            period = "مساءً" if h >= 12 else "صباحاً"
            disp_h = h - 12 if h > 12 else (h if h > 0 else 12)
            peak_txt = f"{disp_h}:00 {period}"
        else:
            peak_txt = "لا يوجد"
        self.card_hour.property("label_widget").setText(peak_txt)
        
        # 4. Sales by channel
        if cashier_filter == "all":
            c.execute("""
                SELECT channel, SUM(total - COALESCE(delivery_fee, 0))
                FROM orders
                WHERE status='COMPLETED' AND created_at BETWEEN ? AND ?
                GROUP BY channel
            """, (start_str, end_str))
        else:
            c.execute("""
                SELECT o.channel, SUM(o.total - COALESCE(o.delivery_fee, 0))
                FROM orders o
                JOIN shifts s ON o.shift_id = s.id
                WHERE o.status='COMPLETED' AND o.created_at BETWEEN ? AND ? AND s.cashier_name = ?
                GROUP BY o.channel
            """, (start_str, end_str, cashier_filter))
            
        channels_sales = dict(c.fetchall())
        cashier_sales = channels_sales.get("CASHIER", 0.0)
        delivery_sales = channels_sales.get("DELIVERY", 0.0)
        
        while self.bars_layout.count():
            child = self.bars_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
                
        c_pct = int((cashier_sales / (cashier_sales + delivery_sales) * 100)) if (cashier_sales + delivery_sales) > 0 else 0
        d_pct = 100 - c_pct if (cashier_sales + delivery_sales) > 0 else 0
        
        c_bar = QFrame(self.bars_container)
        c_bar.setStyleSheet("border: none; background: transparent;")
        c_bar_lyt = QVBoxLayout(c_bar)
        c_bar_lyt.setContentsMargins(0,0,0,0)
        c_bar_lyt.setSpacing(2)
        
        lbl_cb_row = QHBoxLayout()
        lbl_cb = QLabel("الصالة والتيك أواي:", c_bar)
        lbl_cb.setStyleSheet("font-weight: bold; color: #1f2937;")
        lbl_cb_row.addWidget(lbl_cb)
        c_bar_val = QLabel(f"{cashier_sales:,.2f} ج.م ({c_pct}%)", c_bar)
        c_bar_val.setStyleSheet("color: #107c10; font-weight: bold; border: none; background: transparent;")
        c_bar_val.setAlignment(Qt.AlignmentFlag.AlignLeft)
        lbl_cb_row.addWidget(c_bar_val)
        c_bar_lyt.addLayout(lbl_cb_row)
        
        pbar_c = QProgressBar(c_bar)
        pbar_c.setRange(0, 100)
        pbar_c.setValue(c_pct)
        pbar_c.setTextVisible(False)
        pbar_c.setFixedHeight(8)
        pbar_c.setStyleSheet("""
            QProgressBar {
                background-color: #f3f4f6;
                border: 1px solid #e5e7eb;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background-color: #107c10;
                border-radius: 3px;
            }
        """)
        c_bar_lyt.addWidget(pbar_c)
        self.bars_layout.addWidget(c_bar)
        
        d_bar = QFrame(self.bars_container)
        d_bar.setStyleSheet("border: none; background: transparent;")
        d_bar_lyt = QVBoxLayout(d_bar)
        d_bar_lyt.setContentsMargins(0,0,0,0)
        d_bar_lyt.setSpacing(2)
        
        lbl_db_row = QHBoxLayout()
        lbl_db = QLabel("خدمة الدليفري:", d_bar)
        lbl_db.setStyleSheet("font-weight: bold; color: #1f2937;")
        lbl_db_row.addWidget(lbl_db)
        d_bar_val = QLabel(f"{delivery_sales:,.2f} ج.م ({d_pct}%)", d_bar)
        d_bar_val.setStyleSheet("color: #0078d4; font-weight: bold; border: none; background: transparent;")
        d_bar_val.setAlignment(Qt.AlignmentFlag.AlignLeft)
        lbl_db_row.addWidget(d_bar_val)
        d_bar_lyt.addLayout(lbl_db_row)
        
        pbar_d = QProgressBar(d_bar)
        pbar_d.setRange(0, 100)
        pbar_d.setValue(d_pct)
        pbar_d.setTextVisible(False)
        pbar_d.setFixedHeight(8)
        pbar_d.setStyleSheet("""
            QProgressBar {
                background-color: #f3f4f6;
                border: 1px solid #e5e7eb;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background-color: #0078d4;
                border-radius: 3px;
            }
        """)
        d_bar_lyt.addWidget(pbar_d)
        self.bars_layout.addWidget(d_bar)
        
        # 5. Drivers leaderboard
        if cashier_filter == "all":
            c.execute("""
                SELECT d.name, COUNT(o.id) as orders_delivered, SUM(o.total - COALESCE(o.delivery_fee, 0)) as s
                FROM orders o
                JOIN drivers d ON o.driver_id = d.id
                WHERE o.status='COMPLETED' AND o.created_at BETWEEN ? AND ?
                GROUP BY o.driver_id
                ORDER BY orders_delivered DESC
            """, (start_str, end_str))
        else:
            c.execute("""
                SELECT d.name, COUNT(o.id) as orders_delivered, SUM(o.total - COALESCE(o.delivery_fee, 0)) as s
                FROM orders o
                JOIN drivers d ON o.driver_id = d.id
                JOIN shifts s ON o.shift_id = s.id
                WHERE o.status='COMPLETED' AND o.created_at BETWEEN ? AND ? AND s.cashier_name = ?
                GROUP BY o.driver_id
                ORDER BY orders_delivered DESC
            """, (start_str, end_str, cashier_filter))
            
        drivers_data = c.fetchall()
        
        self.leaderboard_table.setRowCount(len(drivers_data))
        for r_idx, (name, count, total) in enumerate(drivers_data):
            self.leaderboard_table.setItem(r_idx, 0, QTableWidgetItem(name))
            self.leaderboard_table.setItem(r_idx, 1, QTableWidgetItem(str(count)))
            self.leaderboard_table.setItem(r_idx, 2, QTableWidgetItem(f"{total:,.2f} ج.م"))
            
        # 6. Detailed History Search
        q = self.search_input.text().strip()
        if cashier_filter == "all":
            if q:
                c.execute("""
                    SELECT o.id, o.created_at, o.channel, o.payment_method, o.total, o.status, COALESCE(cust.name, 'صالة')
                    FROM orders o
                    LEFT JOIN customers cust ON o.customer_id = cust.id
                    LEFT JOIN drivers d ON o.driver_id = d.id
                    WHERE o.created_at BETWEEN ? AND ? AND (o.id LIKE ? OR cust.phone LIKE ? OR cust.name LIKE ? OR d.name LIKE ?)
                    ORDER BY o.id DESC
                """, (start_str, end_str, f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%"))
            else:
                c.execute("""
                    SELECT o.id, o.created_at, o.channel, o.payment_method, o.total, o.status, COALESCE(cust.name, 'صالة')
                    FROM orders o
                    LEFT JOIN customers cust ON o.customer_id = cust.id
                    WHERE o.created_at BETWEEN ? AND ?
                    ORDER BY o.id DESC
                """, (start_str, end_str))
        else:
            if q:
                c.execute("""
                    SELECT o.id, o.created_at, o.channel, o.payment_method, o.total, o.status, COALESCE(cust.name, 'صالة')
                    FROM orders o
                    LEFT JOIN customers cust ON o.customer_id = cust.id
                    LEFT JOIN drivers d ON o.driver_id = d.id
                    JOIN shifts s ON o.shift_id = s.id
                    WHERE o.created_at BETWEEN ? AND ? AND s.cashier_name = ? AND (o.id LIKE ? OR cust.phone LIKE ? OR cust.name LIKE ? OR d.name LIKE ?)
                    ORDER BY o.id DESC
                """, (start_str, end_str, cashier_filter, f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%"))
            else:
                c.execute("""
                    SELECT o.id, o.created_at, o.channel, o.payment_method, o.total, o.status, COALESCE(cust.name, 'صالة')
                    FROM orders o
                    LEFT JOIN customers cust ON o.customer_id = cust.id
                    JOIN shifts s ON o.shift_id = s.id
                    WHERE o.created_at BETWEEN ? AND ? AND s.cashier_name = ?
                    ORDER BY o.id DESC
                """, (start_str, end_str, cashier_filter))
                
        history_rows = c.fetchall()
        conn.close()
        
        self.history_table.setRowCount(len(history_rows))
        for r_idx, (o_id, created_at, chan, pay_method, total, status, name) in enumerate(history_rows):
            self.history_table.setItem(r_idx, 0, QTableWidgetItem(f"#{o_id}"))
            
            dt = datetime.strptime(created_at[:19], "%Y-%m-%d %H:%M:%S")
            self.history_table.setItem(r_idx, 1, QTableWidgetItem(dt.strftime("%d/%m %I:%M %p")))
            
            chan_str = "دليفري" if chan == 'DELIVERY' else "صالة"
            self.history_table.setItem(r_idx, 2, QTableWidgetItem(chan_str))
            
            pay_str = "نقدي كاش" if pay_method == 'CASH' else ("فيزا" if pay_method == 'VISA' else "محفظة")
            self.history_table.setItem(r_idx, 3, QTableWidgetItem(pay_str))
            
            self.history_table.setItem(r_idx, 4, QTableWidgetItem(f"{total:,.2f} ج"))
            
            status_str = "نشط" if status in ('PENDING', 'DISPATCHED') else "مكتمل"
            self.history_table.setItem(r_idx, 5, QTableWidgetItem(status_str))
            
            # Create a cell widget layout for multiple buttons
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(6, 5, 6, 5)
            actions_layout.setSpacing(6)

            btn_view = QPushButton("عرض", actions_widget)
            btn_view.setMinimumSize(78, 34)
            btn_view.setStyleSheet(
                "QPushButton { background: #e6f2ff; color: #0078d4; "
                "border: 1px solid #b3d7ff; border-radius: 6px; "
                "font-size: 11px; padding: 0px 12px; font-weight: bold; } "
                "QPushButton:hover { background: #0078d4; color: white; }"
            )
            btn_view.clicked.connect(lambda checked, idx=o_id: self.view_order_receipt(idx))
            actions_layout.addWidget(btn_view)

            btn_del = QPushButton("حذف", actions_widget)
            btn_del.setMinimumSize(78, 34)
            btn_del.setStyleSheet(
                "QPushButton { background: #fde7e9; color: #a80000; "
                "border: 1px solid #fbc4c4; border-radius: 6px; "
                "font-size: 11px; padding: 0px 12px; font-weight: bold; } "
                "QPushButton:hover { background: #e81123; color: white; }"
            )
            btn_del.clicked.connect(lambda checked, idx=o_id: self.delete_order_from_reports(idx))
            actions_layout.addWidget(btn_del)

            self.history_table.setCellWidget(r_idx, 6, actions_widget)

    def view_order_receipt(self, order_id):
        parent = self.parent()
        if parent and hasattr(parent, 'generate_receipt_text'):
            cashier_receipt = parent.generate_receipt_text(order_id, "نسخة الكاشير (نسخة سابقة)")
            kitchen_receipt = parent.generate_receipt_text(order_id, "نسخة المطبخ (نسخة سابقة)")
            psim = ReceiptSimDialog(order_id, cashier_receipt, kitchen_receipt, parent)
            psim.exec()
        else:
            QMessageBox.warning(self, "خطأ", "لا يمكن تشغيل طابعة المحاكاة للفواتير السابقة.")

    def delete_order_from_reports(self, order_id):
        parent = self.parent()
        if parent and hasattr(parent, 'delete_order_action'):
            parent.delete_order_action(order_id)
            self.load_analytics()

    def delete_all_invoices_action(self):
        # 1. Confirm Deletion
        confirm = QMessageBox.question(
            self, "تأكيد الحذف الكلي الحرج",
            "⚠️ تحذير حرج للغاية!\n\n"
            "أنت على وشك حذف جميع الفواتير والطلبات التاريخية المسجلة بالسيستم نهائياً.\n"
            "هذا الإجراء سيقوم بتصفير المبيعات وتقارير الأداء بالكامل ولا يمكن التراجع عنه.\n\n"
            "هل أنت متأكد تماماً من رغبتك في مسح كافة الفواتير؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
            
        # 3. Perform Deletion
        conn = database.get_connection()
        c = conn.cursor()
        
        try:
            c.execute("DELETE FROM order_items")
            c.execute("DELETE FROM orders")
            # Also reset expected_cash to 0.0 for the active shift since all orders are deleted!
            c.execute("UPDATE shifts SET expected_cash = 0.0, cash_sales=0.0, visa_sales=0.0, wallet_sales=0.0, total_sales=0.0 WHERE closed_at IS NULL")
            c.execute("UPDATE drivers SET unsettled_cash = 0.0")
            conn.commit()
            
            QMessageBox.information(self, "نجاح", "تم حذف ومسح جميع الفواتير بنجاح، وتصفير الإحصائيات بالكامل!")
        except Exception as e:
            conn.rollback()
            QMessageBox.critical(self, "خطأ", f"حدث خطأ أثناء مسح البيانات: {str(e)}")
        finally:
            conn.close()
            
        # 4. Refresh Dashboard UI
        parent = self.parent()
        if parent:
            if hasattr(parent, 'load_pending_delivery_orders'):
                parent.load_pending_delivery_orders()
            if hasattr(parent, 'ensure_active_shift'):
                parent.ensure_active_shift()
                
        self.load_analytics()

    def print_summary_report(self):
        # Generate the print text using current loaded analytics data
        now = datetime.now()
        period_title, period_desc, start_date, end_date = self.get_selected_period()
            
        start_str = start_date.strftime("%Y-%m-%d %H:%M:%S")
        end_str = end_date.strftime("%Y-%m-%d %H:%M:%S")
        
        # Read the current cashier filter value
        cashier_filter = self.cb_cashier.itemData(self.cb_cashier.currentIndex()) if hasattr(self, 'cb_cashier') else "all"
        
        conn = database.get_connection()
        c = conn.cursor()
        
        # Get count and total sales
        if cashier_filter == "all":
            c.execute("SELECT COUNT(*), SUM(total - COALESCE(delivery_fee, 0)) FROM orders WHERE status='COMPLETED' AND created_at BETWEEN ? AND ?", (start_str, end_str))
        else:
            c.execute("""
                SELECT COUNT(*), SUM(o.total - COALESCE(o.delivery_fee, 0))
                FROM orders o 
                JOIN shifts s ON o.shift_id = s.id 
                WHERE o.status='COMPLETED' AND o.created_at BETWEEN ? AND ? AND s.cashier_name = ?
            """, (start_str, end_str, cashier_filter))
            
        row = c.fetchone()
        o_cnt = row[0] if row and row[0] is not None else 0
        total_sales = row[1] if row and row[1] is not None else 0.0
        
        # Get most popular dish
        if cashier_filter == "all":
            c.execute("""
                SELECT COALESCE(oi.item_name, m.name), SUM(oi.quantity) as q
                FROM order_items oi
                LEFT JOIN menu_items m ON oi.menu_item_id = m.id
                JOIN orders o ON oi.order_id = o.id
                WHERE o.status='COMPLETED' AND o.created_at BETWEEN ? AND ?
                GROUP BY oi.menu_item_id
                ORDER BY q DESC LIMIT 1
            """, (start_str, end_str))
        else:
            c.execute("""
                SELECT COALESCE(oi.item_name, m.name), SUM(oi.quantity) as q
                FROM order_items oi
                LEFT JOIN menu_items m ON oi.menu_item_id = m.id
                JOIN orders o ON oi.order_id = o.id
                JOIN shifts s ON o.shift_id = s.id
                WHERE o.status='COMPLETED' AND o.created_at BETWEEN ? AND ? AND s.cashier_name = ?
                GROUP BY oi.menu_item_id
                ORDER BY q DESC LIMIT 1
            """, (start_str, end_str, cashier_filter))
            
        best_dish = c.fetchone()
        best_dish_txt = pos_text(best_dish[0]) if best_dish else "لا يوجد"
        
        # Get peak hour
        if cashier_filter == "all":
            c.execute("""
                SELECT strftime('%H', created_at) as hr, COUNT(*) as c
                FROM orders
                WHERE status='COMPLETED' AND created_at BETWEEN ? AND ?
                GROUP BY hr
                ORDER BY c DESC LIMIT 1
            """, (start_str, end_str))
        else:
            c.execute("""
                SELECT strftime('%H', o.created_at) as hr, COUNT(*) as c
                FROM orders o
                JOIN shifts s ON o.shift_id = s.id
                WHERE o.status='COMPLETED' AND o.created_at BETWEEN ? AND ? AND s.cashier_name = ?
                GROUP BY hr
                ORDER BY c DESC LIMIT 1
            """, (start_str, end_str, cashier_filter))
            
        peak_hour = c.fetchone()
        if peak_hour:
            h = int(peak_hour[0])
            period_meridian = "مساءً" if h >= 12 else "صباحاً"
            disp_h = h - 12 if h > 12 else (h if h > 0 else 12)
            peak_txt = f"{disp_h}:00 {period_meridian}"
        else:
            peak_txt = "لا يوجد"
            
        # Get channels sales distribution
        if cashier_filter == "all":
            c.execute("""
                SELECT channel, SUM(total - COALESCE(delivery_fee, 0))
                FROM orders
                WHERE status='COMPLETED' AND created_at BETWEEN ? AND ?
                GROUP BY channel
            """, (start_str, end_str))
        else:
            c.execute("""
                SELECT o.channel, SUM(o.total - COALESCE(o.delivery_fee, 0))
                FROM orders o
                JOIN shifts s ON o.shift_id = s.id
                WHERE o.status='COMPLETED' AND o.created_at BETWEEN ? AND ? AND s.cashier_name = ?
                GROUP BY o.channel
            """, (start_str, end_str, cashier_filter))
            
        channels_sales = dict(c.fetchall())
        cashier_sales = channels_sales.get("CASHIER", 0.0)
        delivery_sales = channels_sales.get("DELIVERY", 0.0)
        
        total_dist = cashier_sales + delivery_sales
        c_pct = int((cashier_sales / total_dist * 100)) if total_dist > 0 else 0
        d_pct = 100 - c_pct if total_dist > 0 else 0
        
        # Get driver leaderboard
        if cashier_filter == "all":
            c.execute("""
                SELECT d.name, COUNT(o.id) as orders_delivered, SUM(o.total - COALESCE(o.delivery_fee, 0)) as s
                FROM orders o
                JOIN drivers d ON o.driver_id = d.id
                WHERE o.status='COMPLETED' AND o.created_at BETWEEN ? AND ?
                GROUP BY o.driver_id
                ORDER BY orders_delivered DESC
            """, (start_str, end_str))
        else:
            c.execute("""
                SELECT d.name, COUNT(o.id) as orders_delivered, SUM(o.total - COALESCE(o.delivery_fee, 0)) as s
                FROM orders o
                JOIN drivers d ON o.driver_id = d.id
                JOIN shifts s ON o.shift_id = s.id
                WHERE o.status='COMPLETED' AND o.created_at BETWEEN ? AND ? AND s.cashier_name = ?
                GROUP BY o.driver_id
                ORDER BY orders_delivered DESC
            """, (start_str, end_str, cashier_filter))
            
        drivers_data = c.fetchall()
        conn.close()
        
        drivers_text = ""
        for name, count, total in drivers_data:
            drivers_text += f"- {name}: {count} طلب | {total:,.2f} ج.م\n"
        if not drivers_text:
            drivers_text = "- لا يوجد طيارين مسجلين للفترة\n"
            
        current_time_str = now.strftime("%Y-%m-%d %I:%M %p")
        cashier_title_line = f"الوردية: {cashier_filter}" if cashier_filter != "all" else "الوردية: كل الورديات"
        
        report_text = f"""========================================
         تقرير المبيعات {period_title}
              تقرير نظام المبيعات
========================================
التاريخ والوقت: {current_time_str}
الفترة المحددة: {period_desc}
{cashier_title_line}
----------------------------------------
صافي الإيرادات: {total_sales:,.2f} ج.م
عدد الفواتير الناجحة: {o_cnt}
الأكلة الأكثر طلباً: {best_dish_txt}
ساعة الذروة والزحام: {peak_txt}
----------------------------------------
توزيع قنوات البيع:
- صالة وتيك أواي: {cashier_sales:,.2f} ج.م ({c_pct}%)
- خدمة دليفري: {delivery_sales:,.2f} ج.م ({d_pct}%)
----------------------------------------
أداء طيارين الدليفري:
{drivers_text}========================================
             نهاية التقرير
========================================
"""
        # Display the custom print dialog
        dlg = ReportPrintDialog(f"معاينة تقرير المبيعات {period_title}", report_text, self)
        dlg.exec()
