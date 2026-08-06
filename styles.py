# -*- coding: utf-8 -*-
"""
Broost POS - Windows Fluent Light Mode QSS Style Sheets
"""

STYLE_SHEET = """
/* ── GLOBAL BASE ── */
* {
    font-family: 'Segoe UI', 'Almarai', Arial;
    font-size: 13px;
    color: #1a1a1a;
}

QWidget {
    background-color: #f3f3f3;
    color: #1a1a1a;
}

/* Explicit label visibility fix - applies everywhere */
QLabel {
    color: #1a1a1a;
    background: transparent;
}

QCheckBox {
    color: #1a1a1a;
    background: transparent;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #c8c8c8;
    border-radius: 3px;
    background: #ffffff;
}
QCheckBox::indicator:checked {
    background: #0078d4;
    border-color: #0078d4;
}

QGroupBox {
    color: #1a1a1a;
    border: 1px solid #dcdcdc;
    border-radius: 8px;
    margin-top: 10px;
    padding-top: 10px;
    font-weight: bold;
}
QGroupBox::title {
    color: #0078d4;
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}

/* ── TITLE BAR ── */
QWidget#TitleBar, QFrame#TitleBar {
    background-color: #ffffff;
    border-bottom: 1px solid #e5e5e5;
}
QLabel#TitleLabel {
    color: #0078d4;
    font-weight: bold;
    font-size: 14px;
}

/* ── POS PANELS ── */
QFrame#PosPanel {
    background-color: #ffffff;
    border: 1px solid #e5e5e5;
    border-radius: 8px;
}

/* ── PENDING ORDER CARDS ── */
QFrame#PendingOrderCard {
    background-color: #ffffff;
    border: 1px solid #e0e0e0;
    border-radius: 8px;
}
QFrame#PendingOrderCard[delivery="true"] {
    border-left: 5px solid #0078d4;
}
QFrame#PendingOrderCard[warning="true"] {
    border-left: 5px solid #ffb900;
    background-color: #fffaf0;
}
QFrame#PendingOrderCard[critical="true"] {
    border-left: 5px solid #d13438;
    background-color: #fdf3f4;
}

/* ── SCROLL BARS ── */
QScrollBar:vertical {
    border: none;
    background: #f3f3f3;
    width: 8px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #cccccc;
    min-height: 20px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover { background: #0078d4; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar:horizontal { height: 0px; }

/* ── INPUT FIELDS ── */
QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #ffffff;
    border: 1px solid #d9d9d9;
    border-radius: 6px;
    padding: 6px 12px;
    color: #1a1a1a;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid #0078d4;
    background-color: #ffffff;
}
QLineEdit::placeholder { color: #888888; }

/* ── COMBO BOX ── */
QComboBox {
    background-color: #ffffff;
    color: #1a1a1a;
    border: 1px solid #d9d9d9;
    border-radius: 6px;
    padding: 6px 10px;
}
QComboBox:focus { border-color: #0078d4; }
QComboBox QAbstractItemView {
    background-color: #ffffff;
    color: #1a1a1a;
    border: 1px solid #d9d9d9;
    selection-background-color: #0078d4;
    selection-color: #ffffff;
}
QComboBox::drop-down { border: none; }

/* ── SPIN BOX ── */
QSpinBox, QDoubleSpinBox {
    background-color: #ffffff;
    color: #1a1a1a;
    border: 1px solid #d9d9d9;
    border-radius: 6px;
    padding: 5px 8px;
}

/* ── MENU ITEM CARDS ── */
QFrame#MenuItemCard {
    background-color: #ffffff;
    border: 1px solid #e5e5e5;
    border-radius: 8px;
}
QFrame#MenuItemCard:hover {
    border-color: #0078d4;
    background-color: #f9fbfd;
}

/* ── CART ITEM ROWS ── */
QFrame#CartItemRow {
    background-color: #ffffff;
    border: 1px solid #e5e5e5;
    border-radius: 6px;
}

/* ── LABELS ── */
QLabel#PanelTitle {
    font-size: 15px;
    font-weight: bold;
    color: #1a1a1a;
}
QLabel#GrandTotalLabel {
    font-size: 26px;
    font-weight: 800;
    color: #0078d4;
}

/* ── TABLE WIDGET ── */
QTableWidget {
    background-color: #ffffff;
    color: #1a1a1a;
    border: 1px solid #e5e5e5;
    gridline-color: #f3f3f3;
    border-radius: 8px;
}
QTableWidget::item {
    color: #1a1a1a;
    padding: 6px;
    border-bottom: 1px solid #f3f3f3;
}
QTableWidget::item:selected {
    background-color: #e6f2ff;
    color: #0078d4;
}
QHeaderView::section {
    background-color: #f9f9f9;
    color: #0078d4;
    font-weight: bold;
    padding: 8px 6px;
    border: none;
    border-bottom: 1px solid #e5e5e5;
}
QHeaderView { background-color: #f9f9f9; }

/* ── MESSAGE BOX ── */
QMessageBox {
    background-color: #ffffff;
    color: #1a1a1a;
}
QMessageBox QLabel { color: #1a1a1a; }
QMessageBox QPushButton { min-width: 80px; }

/* ── DIALOGS ── */
QDialog {
    background-color: #ffffff;
    border: 1px solid #dcdcdc;
    border-radius: 8px;
}

/* ── TAB WIDGET ── */
QTabWidget::panel {
    border: 1px solid #e5e5e5;
    border-radius: 8px;
    background: #ffffff;
}
QTabBar::tab {
    background: #f3f3f3;
    border: 1px solid #e5e5e5;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    padding: 6px 14px;
    color: #666666;
    font-weight: bold;
}
QTabBar::tab:selected {
    background: #ffffff;
    color: #0078d4;
    border-bottom: 2px solid #0078d4;
}
QTabBar::tab:hover {
    background: #e9e9e9;
}

/* ── BUTTONS - DEFAULT ── */
QPushButton {
    background-color: #0078d4;
    color: #ffffff;
    border: 1px solid #0078d4;
    border-radius: 6px;
    padding: 6px 12px;
    font-weight: bold;
    font-size: 12px;
}
QPushButton:hover { background-color: #106ebe; border-color: #106ebe; }
QPushButton:pressed { background-color: #005a9e; border-color: #005a9e; }
QPushButton:disabled {
    background-color: #f3f3f3;
    color: #a0a0a0;
    border-color: #e5e5e5;
}

/* Dark */
QPushButton#BtnDark {
    background-color: #ffffff;
    color: #374151;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    padding: 6px 12px;
}
QPushButton#BtnDark:hover {
    background-color: #f9fafb;
    border-color: #c5c7cb;
    color: #111827;
}

/* Blue */
QPushButton#BtnBlue {
    background-color: #0078d4;
    color: #ffffff;
    border: 1px solid #0078d4;
    border-radius: 6px;
    padding: 6px 12px;
}
QPushButton#BtnBlue:hover { 
    background-color: #106ebe; 
    border-color: #106ebe;
}

/* Pink */
QPushButton#BtnPink {
    background-color: #fee2e2;
    color: #b91c1c;
    border: 1px solid #fca5a5;
    border-radius: 6px;
    padding: 6px 12px;
}
QPushButton#BtnPink:hover { 
    background-color: #fca5a5; 
    color: #7f1d1d; 
    border-color: #f87171;
}

/* Orange */
QPushButton#BtnOrange {
    background-color: #fef3c7;
    color: #b45309;
    border: 1px solid #fde68a;
    border-radius: 6px;
    padding: 6px 12px;
}
QPushButton#BtnOrange:hover { 
    background-color: #fde68a; 
    color: #78350f; 
    border-color: #fbbf24;
}

/* Channel Toggle */
QPushButton#ChannelBtn {
    background-color: #f9f9f9;
    color: #666666;
    border: 1px solid #d9d9d9;
    padding: 12px;
    font-size: 13px;
    border-radius: 8px;
    font-weight: bold;
}
QPushButton#ChannelBtn[active="true"][mode="cashier"] {
    background-color: #e6f2ff;
    color: #0078d4;
    border-color: #0078d4;
}
QPushButton#ChannelBtn[active="true"][mode="delivery"] {
    background-color: #e6f2ff;
    color: #0078d4;
    border-color: #0078d4;
}

/* ── BROOST 2026 UI REFRESH ── */
QWidget {
    background-color: #f7f7f8;
}

QWidget#TitleBar, QFrame#TitleBar {
    background-color: #ffffff;
    border-bottom: 1px solid #e5e7eb;
}

QFrame#PosPanel {
    background-color: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 14px;
}

QFrame#MenuItemCard {
    background-color: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
}
QFrame#MenuItemCard:hover {
    background-color: #fff7f8;
    border-color: #e89aaa;
}

QFrame#CartItemRow {
    background-color: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
}

QPushButton {
    background-color: #c91432;
    color: #ffffff;
    border: 1px solid #c91432;
    border-radius: 9px;
    padding: 7px 12px;
}
QPushButton:hover {
    background-color: #a90f2a;
    border-color: #a90f2a;
}
QPushButton:pressed {
    background-color: #850a20;
    border-color: #850a20;
}
QPushButton#BtnBlue {
    background-color: #c91432;
    border-color: #c91432;
}
QPushButton#BtnBlue:hover {
    background-color: #a90f2a;
    border-color: #a90f2a;
}

QLabel#GrandTotalLabel {
    color: #c91432;
}

QLabel#SyncStatusBadge {
    background-color: #fff7df;
    color: #8a5200;
    border: 1px solid #f2cf7b;
    border-radius: 9px;
    padding: 6px 10px;
    font-weight: bold;
}
QLabel#SyncStatusBadge[connected="true"] {
    background-color: #e9f8f0;
    color: #14804a;
    border-color: #9ad9b7;
}
QLabel#SyncStatusBadge[connected="false"] {
    background-color: #fff0ef;
    color: #b42318;
    border-color: #f4aaa4;
}

QFrame#PendingOrderCard[online="true"] {
    background-color: #fff7f8;
    border: 1px solid #e89aaa;
    border-left: 5px solid #c91432;
}
QLabel#OnlineOrderStatus {
    background-color: #fff0f3;
    color: #970b22;
    border: 1px solid #ffd1d9;
    border-radius: 7px;
    padding: 5px 8px;
    font-weight: bold;
}

QPushButton#ChannelBtn[active="true"][mode="cashier"],
QPushButton#ChannelBtn[active="true"][mode="delivery"] {
    background-color: #fff0f3;
    color: #970b22;
    border-color: #c91432;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus {
    border-color: #c91432;
}

QScrollBar::handle:vertical:hover {
    background: #c91432;
}

QLabel#DialogTitle {
    color: #c91432;
    font-size: 18px;
    font-weight: bold;
}

QDialog#OnlineOrderAlert {
    background-color: #f7f7f8;
    border: 3px solid #c91432;
    border-radius: 18px;
}
QFrame#OnlineAlertHeader {
    background-color: #fff0f3;
    border: 1px solid #ffd1d9;
    border-radius: 14px;
}
QLabel#OnlineAlertIcon {
    background-color: #c91432;
    color: #ffffff;
    border-radius: 29px;
    font-size: 24px;
}
QLabel#OnlineAlertTitle {
    color: #970b22;
    font-size: 22px;
    font-weight: bold;
}
QLabel#OnlineAlertSubtitle {
    color: #6b2635;
    font-size: 14px;
}
QLabel#OnlineAlertTotal {
    color: #c91432;
    font-size: 24px;
    font-weight: bold;
}
QFrame#OnlineAlertDetails, QFrame#OnlineAlertItems {
    background-color: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 14px;
}
QLabel#OnlineAlertRowLabel {
    color: #6b7280;
    font-weight: bold;
}
QLabel#OnlineAlertRowValue {
    color: #18181b;
    font-weight: bold;
}
QLabel#OnlineAlertSectionTitle {
    color: #c91432;
    font-size: 16px;
    font-weight: bold;
}
QLabel#OnlineAlertItem {
    color: #18181b;
    background-color: #f7f7f8;
    border: 1px solid #e5e7eb;
    border-radius: 9px;
    padding: 9px;
    font-weight: bold;
}
QPushButton#OnlineAcceptButton {
    background-color: #14804a;
    border-color: #14804a;
    font-size: 15px;
}
QPushButton#OnlineAcceptButton:hover {
    background-color: #0f673c;
    border-color: #0f673c;
}
QPushButton#OnlineRejectButton {
    background-color: #fff0ef;
    color: #b42318;
    border-color: #f4aaa4;
    font-size: 14px;
}

/* ── BROOST MODERN LIGHT SYSTEM ── */
* {
    font-family: 'Segoe UI Variable Text', 'Segoe UI', 'Tahoma';
    color: #27272a;
}
QWidget {
    background-color: #f5f5f3;
}
QLabel {
    color: #27272a;
    background: transparent;
}
QLabel#MutedText {
    color: #71717a;
    font-size: 12px;
}

QWidget#TitleBar, QFrame#TitleBar {
    background-color: #ffffff;
    border-bottom: 1px solid #e7e5e4;
}
QFrame#HeaderBrand {
    background-color: #ffffff;
    border: 1px solid #e7e5e4;
    border-radius: 11px;
}
QFrame#PosPanel {
    background-color: #ffffff;
    border: 1px solid #e7e5e4;
    border-radius: 16px;
}

QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: #ffffff;
    color: #18181b;
    border: 1px solid #dedbd7;
    border-radius: 10px;
    padding: 7px 11px;
    selection-background-color: #be123c;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 2px solid #be123c;
    padding: 6px 10px;
}
QLineEdit::placeholder {
    color: #a1a1aa;
}

QPushButton {
    background-color: #be123c;
    color: #ffffff;
    border: 1px solid #be123c;
    border-radius: 10px;
    padding: 8px 13px;
    font-weight: 700;
}
QPushButton:hover {
    background-color: #9f1239;
    border-color: #9f1239;
}
QPushButton:pressed {
    background-color: #881337;
    border-color: #881337;
}
QPushButton:disabled {
    background-color: #f0efed;
    color: #a1a1aa;
    border-color: #e7e5e4;
}
QPushButton#BtnBlue {
    background-color: #be123c;
    border-color: #be123c;
}
QPushButton#BtnBlue:hover {
    background-color: #9f1239;
    border-color: #9f1239;
}
QPushButton#BtnDark {
    background-color: #ffffff;
    color: #3f3f46;
    border: 1px solid #d6d3d1;
}
QPushButton#BtnDark:hover {
    background-color: #f7f6f4;
    color: #18181b;
    border-color: #a8a29e;
}
QPushButton#BtnOrange {
    background-color: #fff7e6;
    color: #9a5b00;
    border: 1px solid #f0cf91;
}
QPushButton#BtnOrange:hover {
    background-color: #ffedc8;
    color: #7c4700;
    border-color: #e5b75e;
}
QPushButton#BtnPink {
    background-color: #fff1f2;
    color: #be123c;
    border: 1px solid #fecdd3;
}
QPushButton#BtnPink:hover {
    background-color: #ffe4e6;
    color: #9f1239;
    border-color: #fda4af;
}
QPushButton#BtnOffer {
    background-color: #18181b;
    color: #ffffff;
    border: 1px solid #18181b;
    border-radius: 10px;
    font-weight: 800;
}
QPushButton#BtnOffer:hover {
    background-color: #be123c;
    border-color: #be123c;
}

QPushButton#ChannelBtn {
    background-color: #f7f6f4;
    color: #52525b;
    border: 1px solid #e7e5e4;
    border-radius: 11px;
    padding: 11px;
}
QPushButton#ChannelBtn[active="true"][mode="cashier"],
QPushButton#ChannelBtn[active="true"][mode="delivery"] {
    background-color: #fff1f2;
    color: #9f1239;
    border-color: #be123c;
}

QFrame#MenuItemCard, QFrame#CartItemRow, QFrame#PendingOrderCard {
    background-color: #ffffff;
    border: 1px solid #e7e5e4;
    border-radius: 13px;
}
QFrame#MenuItemCard:hover {
    background-color: #fffafb;
    border-color: #e7a4b5;
}
QLabel#MenuEmptyState {
    color: #71717a;
    background-color: #fafaf9;
    border: 1px dashed #d6d3d1;
    border-radius: 14px;
    padding: 28px;
    font-size: 14px;
}

QTableWidget {
    background-color: #ffffff;
    color: #27272a;
    border: 1px solid #e7e5e4;
    gridline-color: #f2f1ef;
    border-radius: 12px;
}
QTableWidget::item {
    padding: 8px;
    border-bottom: 1px solid #f2f1ef;
}
QTableWidget::item:selected {
    background-color: #fff1f2;
    color: #9f1239;
}
QHeaderView::section {
    background-color: #fafaf9;
    color: #52525b;
    border: none;
    border-bottom: 1px solid #e7e5e4;
    padding: 9px 7px;
    font-weight: 800;
}

QTabWidget::panel {
    background-color: #ffffff;
    border: 1px solid #e7e5e4;
    border-radius: 12px;
}
QTabBar::tab {
    background-color: #f5f5f3;
    color: #71717a;
    border: 1px solid #e7e5e4;
    border-bottom: none;
    padding: 8px 15px;
}
QTabBar::tab:selected {
    background-color: #ffffff;
    color: #be123c;
    border-bottom: 2px solid #be123c;
}

QCheckBox {
    color: #27272a;
    spacing: 9px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    background-color: #ffffff;
    border: 1px solid #c9c5c1;
    border-radius: 5px;
}
QCheckBox::indicator:checked {
    background-color: #be123c;
    border-color: #be123c;
}

QScrollBar:vertical {
    background: transparent;
    width: 9px;
    margin: 3px;
}
QScrollBar::handle:vertical {
    background: #d6d3d1;
    min-height: 28px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #be123c;
}

QDialog {
    background-color: #ffffff;
    border: 1px solid #dedbd7;
    border-radius: 16px;
}
QLabel#DialogTitle {
    color: #18181b;
    font-size: 21px;
    font-weight: 900;
}
QScrollArea#OffersScroll {
    background-color: #fafaf9;
    border: 1px solid #e7e5e4;
    border-radius: 14px;
}
QLabel#OffersSectionTitle {
    color: #9f1239;
    font-size: 13px;
    font-weight: 900;
    padding: 12px 4px 5px 4px;
}
QFrame#OfferChoiceRow {
    background-color: #ffffff;
    border: 1px solid #e7e5e4;
    border-radius: 11px;
}
QLabel#OfferPrice {
    color: #be123c;
    font-weight: 900;
}
"""
