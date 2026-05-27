# -*- coding: utf-8 -*-
"""
Broost POS - Cyber-Brutalist QSS Style Sheets
"""

STYLE_SHEET = """
/* ── GLOBAL BASE ── */
* {
    font-family: 'Almarai', 'Segoe UI', Arial;
    font-size: 13px;
    color: #ffffff;
}

QWidget {
    background-color: #0e1e1d;
    color: #ffffff;
}

/* Explicit label visibility fix - applies everywhere */
QLabel {
    color: #ffffff;
    background: transparent;
}

QCheckBox {
    color: #ffffff;
    background: transparent;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #263434;
    border-radius: 3px;
    background: #050a0a;
}
QCheckBox::indicator:checked {
    background: #8cffa7;
    border-color: #8cffa7;
}

QGroupBox {
    color: #ffffff;
    border: 1px solid #263434;
    border-radius: 8px;
    margin-top: 10px;
    padding-top: 10px;
    font-weight: bold;
}
QGroupBox::title {
    color: #a8deff;
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}

/* ── TITLE BAR ── */
QWidget#TitleBar, QFrame#TitleBar {
    background-color: #081211;
    border-bottom: 1px solid #263434;
}
QLabel#TitleLabel {
    color: #8cffa7;
    font-weight: bold;
    font-size: 14px;
}

/* ── POS PANELS ── */
QFrame#PosPanel {
    background-color: rgba(255, 255, 255, 0.03);
    border: 1px solid #263434;
    border-radius: 12px;
}

/* ── PENDING ORDER CARDS ── */
QFrame#PendingOrderCard {
    background-color: rgba(255, 255, 255, 0.02);
    border: 1px solid #263434;
    border-radius: 8px;
}
QFrame#PendingOrderCard[delivery="true"] {
    border-left: 4px solid #a8deff;
}
QFrame#PendingOrderCard[warning="true"] {
    border-left: 4px solid #ffa8f6;
    background-color: rgba(255, 168, 246, 0.04);
}
QFrame#PendingOrderCard[critical="true"] {
    border-left: 4px solid #ff5050;
    background-color: rgba(255, 80, 80, 0.08);
}

/* ── SCROLL BARS ── */
QScrollBar:vertical {
    border: none;
    background: #0e1e1d;
    width: 6px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #263434;
    min-height: 20px;
    border-radius: 3px;
}
QScrollBar::handle:vertical:hover { background: #8cffa7; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar:horizontal { height: 0px; }

/* ── INPUT FIELDS ── */
QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #050a0a;
    border: 1px solid #263434;
    border-radius: 6px;
    padding: 8px 12px;
    color: #ffffff;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #a8deff;
    background-color: #081514;
}
QLineEdit::placeholder { color: rgba(255,255,255,0.3); }

/* ── COMBO BOX ── */
QComboBox {
    background-color: #050a0a;
    color: #ffffff;
    border: 1px solid #263434;
    border-radius: 6px;
    padding: 6px 10px;
}
QComboBox:focus { border-color: #a8deff; }
QComboBox QAbstractItemView {
    background-color: #081211;
    color: #ffffff;
    border: 1px solid #263434;
    selection-background-color: #263434;
    selection-color: #8cffa7;
}
QComboBox::drop-down { border: none; }

/* ── SPIN BOX ── */
QSpinBox, QDoubleSpinBox {
    background-color: #050a0a;
    color: #ffffff;
    border: 1px solid #263434;
    border-radius: 6px;
    padding: 5px 8px;
}

/* ── MENU ITEM CARDS ── */
QFrame#MenuItemCard {
    background-color: rgba(255, 255, 255, 0.03);
    border: 1px solid #263434;
    border-radius: 12px;
}
QFrame#MenuItemCard:hover {
    border-color: rgba(140,255,167,0.5);
    background-color: rgba(140,255,167,0.04);
}

/* ── CART ITEM ROWS ── */
QFrame#CartItemRow {
    background-color: rgba(255, 255, 255, 0.025);
    border: 1px solid #263434;
    border-radius: 6px;
}

/* ── LABELS ── */
QLabel#PanelTitle {
    font-size: 15px;
    font-weight: 800;
    color: #ffffff;
}
QLabel#GrandTotalLabel {
    font-size: 26px;
    font-weight: 900;
    color: #8cffa7;
}

/* ── TABLE WIDGET ── */
QTableWidget {
    background-color: transparent;
    color: #ffffff;
    border: 1px solid #263434;
    gridline-color: #263434;
    border-radius: 8px;
}
QTableWidget::item {
    color: #ffffff;
    padding: 6px;
    border-bottom: 1px solid #263434;
}
QTableWidget::item:selected {
    background-color: rgba(140,255,167,0.12);
    color: #8cffa7;
}
QHeaderView::section {
    background-color: #081211;
    color: #a8deff;
    font-weight: bold;
    padding: 8px 6px;
    border: none;
    border-bottom: 1px solid #263434;
}
QHeaderView { background-color: #081211; }

/* ── MESSAGE BOX ── */
QMessageBox {
    background-color: #0e1e1d;
    color: #ffffff;
}
QMessageBox QLabel { color: #ffffff; }
QMessageBox QPushButton { min-width: 80px; }

/* ── DIALOGS ── */
QDialog {
    background-color: #0e1e1d;
    border: 1px solid #263434;
    border-radius: 12px;
}

/* ── TAB WIDGET ── */
QTabWidget::panel {
    border: 1px solid #263434;
    border-radius: 8px;
    background: #0e1e1d;
}
QTabBar::tab {
    background: rgba(255,255,255,0.03);
    border: 1px solid #263434;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 6px 14px;
    color: rgba(255,255,255,0.6);
    font-weight: bold;
}
QTabBar::tab:selected {
    background: #0e1e1d;
    color: #8cffa7;
    border-bottom: 2px solid #8cffa7;
}
QTabBar::tab:hover {
    background: rgba(255,255,255,0.08);
}

/* ── BUTTONS - DEFAULT ── */
QPushButton {
    background-color: #dcffe4;
    color: #0e1e1d;
    border: 1px solid rgba(140,255,167,0.4);
    border-radius: 6px;
    padding: 6px 12px;
    font-weight: 900;
    font-size: 12px;
}
QPushButton:hover { background-color: #8cffa7; }
QPushButton:pressed { background-color: #6ee68c; }
QPushButton:disabled {
    background-color: rgba(255,255,255,0.04);
    color: rgba(255,255,255,0.25);
    border-color: #263434;
}

/* Dark */
QPushButton#BtnDark {
    background-color: rgba(255,255,255,0.04);
    color: #ffffff;
    border: 1px solid #263434;
}
QPushButton#BtnDark:hover {
    background-color: #263434;
    border-color: #8cffa7;
    color: #8cffa7;
}

/* Blue */
QPushButton#BtnBlue {
    background-color: rgba(168,222,255,0.12);
    color: #a8deff;
    border: 1px solid rgba(168,222,255,0.35);
}
QPushButton#BtnBlue:hover { background-color: #a8deff; color: #0e1e1d; }

/* Pink */
QPushButton#BtnPink {
    background-color: rgba(255,168,246,0.12);
    color: #ffa8f6;
    border: 1px solid rgba(255,168,246,0.35);
}
QPushButton#BtnPink:hover { background-color: #ffa8f6; color: #0e1e1d; }

/* Orange */
QPushButton#BtnOrange {
    background-color: rgba(255,217,168,0.12);
    color: #ffd9a8;
    border: 1px solid rgba(255,217,168,0.35);
}
QPushButton#BtnOrange:hover { background-color: #ffd9a8; color: #0e1e1d; }

/* Channel Toggle */
QPushButton#ChannelBtn {
    background-color: rgba(255,255,255,0.03);
    color: rgba(255,255,255,0.45);
    border: 1px solid #263434;
    padding: 12px;
    font-size: 13px;
    border-radius: 8px;
}
QPushButton#ChannelBtn[active="true"][mode="cashier"] {
    background-color: rgba(140,255,167,0.12);
    color: #8cffa7;
    border-color: rgba(140,255,167,0.5);
}
QPushButton#ChannelBtn[active="true"][mode="delivery"] {
    background-color: rgba(168,222,255,0.12);
    color: #a8deff;
    border-color: rgba(168,222,255,0.5);
}
"""
