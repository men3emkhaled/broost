# -*- coding: utf-8 -*-
"""Broost POS - Item Details Picker Dialog (sizes, extras, qty)"""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QWidget, QMessageBox
)
import database
from core.display_text import pos_text
from styles import STYLE_SHEET


class ItemDetailsPickerDialog(QDialog):
    """Allows selecting sizes, optional extras, and quantity before adding to cart."""
    def __init__(self, item_id, item_name, base_price, parent=None):
        super().__init__(parent)
        self.setWindowTitle("خيارات الصنف")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setFixedSize(420, 480)
        self.setStyleSheet(STYLE_SHEET)
        
        self.item_id = item_id
        self.item_name = pos_text(item_name) or "صنف"
        self.base_price = base_price
        
        self.selected_size = "عادي"
        self.size_offset = 0.0
        self.selected_extras = {} # name -> price
        self.quantity = 1
        
        self.init_ui()
        self.load_options()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)
        
        # Item Header Title
        header_label = QLabel(self.item_name, self)
        header_label.setStyleSheet("font-size: 18px; font-weight: 800; color: #0078d4;")
        layout.addWidget(header_label)
        
        # [1] Sizes section
        sizes_label = QLabel("اختر الحجم أو الطعم:", self)
        sizes_label.setStyleSheet("font-weight: bold; color: #1a1a1a;")
        layout.addWidget(sizes_label)
        
        self.sizes_area = QWidget(self)
        self.sizes_layout = QHBoxLayout(self.sizes_area)
        self.sizes_layout.setContentsMargins(0, 0, 0, 0)
        self.sizes_layout.setSpacing(6)
        layout.addWidget(self.sizes_area)
        
        # [2] Extras section
        extras_label = QLabel("إضافات إضافية (اختياري):", self)
        extras_label.setStyleSheet("font-weight: bold; color: #1a1a1a;")
        layout.addWidget(extras_label)
        
        self.extras_scroll = QScrollArea(self)
        self.extras_scroll.setWidgetResizable(True)
        self.extras_scroll.setStyleSheet("background: #f9f9f9; border: 1px solid #e5e5e5;")
        self.extras_container = QWidget()
        self.extras_layout = QVBoxLayout(self.extras_container)
        self.extras_layout.setContentsMargins(8, 8, 8, 8)
        self.extras_layout.setSpacing(6)
        self.extras_scroll.setWidget(self.extras_container)
        layout.addWidget(self.extras_scroll)
        
        # [3] Quantity counter row
        qty_row = QHBoxLayout()
        qty_lbl = QLabel("الكمية المطلوبة:", self)
        qty_lbl.setStyleSheet("font-weight: bold; color: #1a1a1a;")
        qty_row.addWidget(qty_lbl)
        qty_row.addStretch()
        
        btn_minus = QPushButton("-", self)
        btn_minus.setFixedSize(36, 32)
        btn_minus.setObjectName("BtnDark")
        btn_minus.clicked.connect(lambda: self.adjust_qty(-1))
        
        self.qty_val_lbl = QLabel("1", self)
        self.qty_val_lbl.setStyleSheet("font-size: 16px; font-weight: bold; min-width: 30px; color: #1a1a1a;")
        self.qty_val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        btn_plus = QPushButton("+", self)
        btn_plus.setFixedSize(36, 32)
        btn_plus.setObjectName("BtnDark")
        btn_plus.clicked.connect(lambda: self.adjust_qty(1))
        
        qty_row.addWidget(btn_minus)
        qty_row.addWidget(self.qty_val_lbl)
        qty_row.addWidget(btn_plus)
        layout.addLayout(qty_row)
        
        # Footer Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        
        self.btn_add = QPushButton("إضافة إلى السلة", self)
        self.btn_add.clicked.connect(self.accept)
        
        btn_cancel = QPushButton("تراجع", self)
        btn_cancel.setObjectName("BtnDark")
        btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(self.btn_add)
        layout.addLayout(btn_layout)

    def load_options(self):
        conn = database.get_connection()
        c = conn.cursor()
        
        # Load sizes
        c.execute("SELECT name, price_offset FROM menu_item_sizes WHERE item_id=?", (self.item_id,))
        sizes = c.fetchall()
        
        # Draw size buttons
        self.size_buttons = []
        if sizes:
            for name, offset in sizes:
                display_name = pos_text(name) or "عادي"
                btn = QPushButton(f"{display_name} (+{offset} ج.م)", self)
                btn.setCheckable(True)
                btn.setProperty("name", display_name)
                btn.setProperty("offset", offset)
                btn.setStyleSheet("QPushButton { background-color: #ffffff; border: 1px solid #cccccc; color: #1a1a1a; } QPushButton:checked { background-color: #e6f2ff; color: #0078d4; border-color: #0078d4; }")
                btn.clicked.connect(lambda checked, b=btn: self.select_size(b))
                
                self.sizes_layout.addWidget(btn)
                self.size_buttons.append(btn)
                
            # Default check first
            self.size_buttons[0].setChecked(True)
            self.selected_size = self.size_buttons[0].property("name")
            self.size_offset = self.size_buttons[0].property("offset")
        else:
            # Standalone default size
            lbl = QLabel("حجم موحد قياسي", self)
            lbl.setStyleSheet("color: #616161;")
            self.sizes_layout.addWidget(lbl)
            
        # Load extras
        c.execute("SELECT name, price FROM menu_item_extras WHERE item_id=?", (self.item_id,))
        extras = c.fetchall()
        
        self.extra_buttons = []
        if extras:
            for name, price in extras:
                display_name = pos_text(name) or "إضافة"
                btn = QPushButton(f"{display_name} (+{price} ج.م)", self)
                btn.setCheckable(True)
                btn.setProperty("name", display_name)
                btn.setProperty("price", price)
                btn.setStyleSheet("QPushButton { text-align: right; background-color: #ffffff; border: 1px solid #cccccc; color: #1a1a1a; padding-right: 12px; } QPushButton:checked { background-color: #e6f2ff; color: #0078d4; border-color: #0078d4; }")
                btn.clicked.connect(lambda checked, b=btn: self.toggle_extra(b))
                
                self.extras_layout.addWidget(btn)
                self.extra_buttons.append(btn)
            self.extras_layout.addStretch()
        else:
            lbl = QLabel("لا توجد إضافات متاحة لهذا الصنف", self)
            lbl.setStyleSheet("color: #616161; font-style: italic;")
            self.extras_layout.addWidget(lbl)
            
        conn.close()


    def select_size(self, clicked_btn):
        for btn in self.size_buttons:
            btn.setChecked(btn == clicked_btn)
            
        self.selected_size = clicked_btn.property("name")
        self.size_offset = float(clicked_btn.property("offset"))

    def toggle_extra(self, clicked_btn):
        name = clicked_btn.property("name")
        price = float(clicked_btn.property("price"))
        
        if clicked_btn.isChecked():
            self.selected_extras[name] = price
        else:
            if name in self.selected_extras:
                del self.selected_extras[name]

    def adjust_qty(self, delta):
        new_qty = self.quantity + delta
        if new_qty >= 1:
            self.quantity = new_qty
            self.qty_val_lbl.setText(str(self.quantity))

    def prefill_selections(self, size_name, qty, extras):
        self.quantity = qty
        self.qty_val_lbl.setText(str(qty))
        
        # Select size
        for btn in self.size_buttons:
            if btn.property("name") == size_name:
                btn.setChecked(True)
                self.selected_size = size_name
                self.size_offset = float(btn.property("offset") or 0.0)
            else:
                btn.setChecked(False)
                
        # Select extras
        self.selected_extras = extras.copy()
        for btn in self.extra_buttons:
            name = btn.property("name")
            if name in extras:
                btn.setChecked(True)
            else:
                btn.setChecked(False)
