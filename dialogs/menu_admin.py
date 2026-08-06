# -*- coding: utf-8 -*-
"""Broost POS - Menu Items & Categories Administration Dialog"""
import sqlite3
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QScrollArea, QWidget, QMessageBox,
    QGridLayout, QInputDialog
)
import database
from core.display_text import pos_text
from styles import STYLE_SHEET


class MenuAdminDialog(QDialog):
    """Admin Panel to manage categories and items: add, delete, rename, update prices, toggle availability."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("إدارة المنيو والتسعير")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setFixedSize(880, 600)
        self.setStyleSheet(STYLE_SHEET)
        
        self.selected_category_id = None
        self.category_buttons = {}  # cat_id -> QPushButton
        
        self.init_ui()
        self.load_categories()
        
    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)
        
        # Header
        header = QHBoxLayout()
        title = QLabel("⚙️ لوحة التحكم وإدارة أقسام وأصناف المنيو", self)
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #0078d4;")
        header.addWidget(title)
        
        header.addStretch()
        
        btn_close = QPushButton("✕", self)
        btn_close.setFixedSize(32, 32)
        btn_close.setStyleSheet("QPushButton { background: #f3f4f6; color: #4b5563; border: 1px solid #e5e7eb; border-radius: 6px; font-weight: bold; font-size: 14px; } QPushButton:hover { background: #fee2e2; color: #dc2626; border-color: #fca5a5; }")
        btn_close.clicked.connect(self.accept)
        header.addWidget(btn_close)
        main_layout.addLayout(header)
        
        # Two Columns Splitter Layout
        splitter_layout = QHBoxLayout()
        splitter_layout.setSpacing(14)
        
        # ==========================================
        # 1. Right Column: Categories Management
        # ==========================================
        right_panel = QVBoxLayout()
        right_panel.setSpacing(8)
        
        lbl_cat_title = QLabel("📂 أقسام المنيو الأساسية", self)
        lbl_cat_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #374151;")
        right_panel.addWidget(lbl_cat_title)
        
        # Add category input & button
        add_cat_box = QHBoxLayout()
        self.txt_new_cat = QLineEdit(self)
        self.txt_new_cat.setPlaceholderText("اسم القسم الجديد...")
        self.txt_new_cat.setFixedHeight(32)
        self.txt_new_cat.setStyleSheet("QLineEdit { background: white; border: 1px solid #d1d5db; border-radius: 6px; padding: 0 8px; } QLineEdit:focus { border-color: #0078d4; }")
        add_cat_box.addWidget(self.txt_new_cat)
        
        btn_add_cat = QPushButton("➕", self)
        btn_add_cat.setFixedSize(32, 32)
        btn_add_cat.setStyleSheet("QPushButton { background-color: #0078d4; color: white; border: none; border-radius: 6px; font-weight: bold; } QPushButton:hover { background-color: #106ebe; }")
        btn_add_cat.clicked.connect(self.add_category_action)
        add_cat_box.addWidget(btn_add_cat)
        right_panel.addLayout(add_cat_box)
        
        # Scroll area for categories list
        self.cat_scroll = QScrollArea(self)
        self.cat_scroll.setWidgetResizable(True)
        self.cat_scroll.setFixedWidth(280)
        self.cat_scroll.setStyleSheet("background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px;")
        
        self.cat_container = QWidget()
        self.cat_layout = QVBoxLayout(self.cat_container)
        self.cat_layout.setContentsMargins(8, 8, 8, 8)
        self.cat_layout.setSpacing(6)
        self.cat_scroll.setWidget(self.cat_container)
        right_panel.addWidget(self.cat_scroll)
        
        splitter_layout.addLayout(right_panel, stretch=1)
        
        # ==========================================
        # 2. Left Column: Product Items Management
        # ==========================================
        left_panel = QVBoxLayout()
        left_panel.setSpacing(8)
        
        self.lbl_items_title = QLabel("🍔 أصناف القسم المحدد", self)
        self.lbl_items_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #374151;")
        left_panel.addWidget(self.lbl_items_title)
        
        # Inline Add Product Form
        self.add_prod_frame = QFrame(self)
        self.add_prod_frame.setStyleSheet("QFrame { background-color: #f0f7ff; border: 1px solid #cce3ff; border-radius: 8px; padding: 8px; }")
        add_prod_layout = QHBoxLayout(self.add_prod_frame)
        add_prod_layout.setContentsMargins(6, 6, 6, 6)
        add_prod_layout.setSpacing(8)
        
        self.txt_new_prod_name = QLineEdit(self)
        self.txt_new_prod_name.setPlaceholderText("اسم المنتج الجديد...")
        self.txt_new_prod_name.setFixedHeight(32)
        self.txt_new_prod_name.setStyleSheet("QLineEdit { background: white; border: 1px solid #d1d5db; border-radius: 6px; padding: 0 8px; } QLineEdit:focus { border-color: #0078d4; }")
        add_prod_layout.addWidget(self.txt_new_prod_name, stretch=3)
        
        self.txt_new_prod_price = QLineEdit(self)
        self.txt_new_prod_price.setPlaceholderText("السعر...")
        self.txt_new_prod_price.setFixedWidth(80)
        self.txt_new_prod_price.setFixedHeight(32)
        self.txt_new_prod_price.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.txt_new_prod_price.setStyleSheet("QLineEdit { background: white; border: 1px solid #d1d5db; border-radius: 6px; } QLineEdit:focus { border-color: #0078d4; }")
        add_prod_layout.addWidget(self.txt_new_prod_price, stretch=1)
        
        btn_add_prod = QPushButton("➕ إضافة صنف", self)
        btn_add_prod.setFixedHeight(32)
        btn_add_prod.setStyleSheet("QPushButton { background-color: #107c10; color: white; border: none; border-radius: 6px; font-weight: bold; padding: 0 12px; } QPushButton:hover { background-color: #0b5a0b; }")
        btn_add_prod.clicked.connect(self.add_product_action)
        add_prod_layout.addWidget(btn_add_prod, stretch=1)
        
        left_panel.addWidget(self.add_prod_frame)
        
        # Scroll area for items list
        self.items_scroll = QScrollArea(self)
        self.items_scroll.setWidgetResizable(True)
        self.items_scroll.setStyleSheet("background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px;")
        
        self.items_container = QWidget()
        self.items_layout = QVBoxLayout(self.items_container)
        self.items_layout.setContentsMargins(10, 10, 10, 10)
        self.items_layout.setSpacing(8)
        self.items_scroll.setWidget(self.items_container)
        left_panel.addWidget(self.items_scroll)
        
        splitter_layout.addLayout(left_panel, stretch=2)
        
        main_layout.addLayout(splitter_layout)
        
        # Bottom Save & Close button
        btn_save_all = QPushButton("💾 تم الانتهاء وحفظ جميع التغييرات", self)
        btn_save_all.setFixedHeight(40)
        btn_save_all.setStyleSheet("QPushButton { background-color: #0078d4; color: white; border: none; border-radius: 6px; font-weight: bold; font-size: 14px; } QPushButton:hover { background-color: #106ebe; }")
        btn_save_all.clicked.connect(self.accept)
        main_layout.addWidget(btn_save_all)

    def load_categories(self):
        # Clear category layout
        for i in reversed(range(self.cat_layout.count())):
            item = self.cat_layout.itemAt(i)
            if item.widget():
                item.widget().setParent(None)
                
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("SELECT id, name FROM categories ORDER BY sort_order ASC, id ASC")
        categories = c.fetchall()
        conn.close()
        
        self.category_buttons.clear()
        
        for cat_id, name in categories:
            display_name = pos_text(name) or "قسم"
            cat_row = QFrame(self.cat_container)
            cat_row.setStyleSheet("background: white; border: 1px solid #e5e7eb; border-radius: 6px; padding: 2px;")
            r_layout = QHBoxLayout(cat_row)
            r_layout.setContentsMargins(4, 4, 4, 4)
            r_layout.setSpacing(6)
            
            # Category selection button
            btn_select = QPushButton(display_name, cat_row)
            btn_select.setFixedHeight(32)
            btn_select.setProperty("cat_id", cat_id)
            btn_select.setProperty("cat_name", display_name)
            self.category_buttons[cat_id] = btn_select
            btn_select.clicked.connect(lambda checked, idx=cat_id: self.select_category(idx))
            r_layout.addWidget(btn_select, stretch=1)
            
            # Delete button for category
            btn_del = QPushButton("🗑️", cat_row)
            btn_del.setFixedSize(28, 28)
            btn_del.setStyleSheet("QPushButton { background: #fde7e9; color: #a80000; border: 1px solid #fbc4c4; border-radius: 4px; font-size: 11px; } QPushButton:hover { background: #e81123; color: white; }")
            btn_del.clicked.connect(lambda checked, idx=cat_id, n=display_name: self.delete_category_action(idx, n))
            r_layout.addWidget(btn_del)
            
            self.cat_layout.addWidget(cat_row)
            
        self.cat_layout.addStretch()
        
        # Select first category if we have categories
        if categories:
            if self.selected_category_id not in [cat[0] for cat in categories]:
                self.select_category(categories[0][0])
            else:
                self.select_category(self.selected_category_id)
        else:
            self.selected_category_id = None
            self.update_category_buttons_style()
            self.load_category_items()

    def select_category(self, cat_id):
        self.selected_category_id = cat_id
        self.update_category_buttons_style()
        
        # Update products list
        self.load_category_items()

    def update_category_buttons_style(self):
        for cat_id, btn in self.category_buttons.items():
            name = btn.property("cat_name")
            if cat_id == self.selected_category_id:
                btn.setText(f"⭐ {name}")
                btn.setStyleSheet("QPushButton { background-color: #0078d4; color: white; border: none; border-radius: 4px; font-weight: bold; text-align: right; padding-right: 8px; }")
            else:
                btn.setText(name)
                btn.setStyleSheet("QPushButton { background-color: white; color: #1f2937; border: none; text-align: right; padding-right: 8px; } QPushButton:hover { background-color: #f3f4f6; }")

    def add_category_action(self):
        name = self.txt_new_cat.text().strip()
        if not name:
            QMessageBox.warning(self, "خطأ", "برجاء كتابة اسم القسم أولاً.")
            return
            
        conn = database.get_connection()
        c = conn.cursor()
        try:
            c.execute("INSERT INTO categories (name, sort_order) VALUES (?, 100)", (name,))
            conn.commit()
            new_id = c.lastrowid
            self.txt_new_cat.clear()
            self.selected_category_id = new_id
            self.load_categories()
        except sqlite3.IntegrityError:
            QMessageBox.critical(self, "خطأ", "هذا القسم موجود بالفعل بالسيستم.")
        finally:
            conn.close()

    def delete_category_action(self, cat_id, name):
        confirm = QMessageBox.question(
            self, "حذف القسم",
            f"⚠️ هل أنت متأكد من حذف القسم '{name}' بالكامل؟\n\n"
            "هذا سيؤدي لحذف جميع الأصناف والمنتجات التابعة لهذا القسم نهائياً من المنيو!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
            
        conn = database.get_connection()
        c = conn.cursor()
        try:
            # Delete items belonging to this category
            c.execute("DELETE FROM menu_items WHERE category_id=?", (cat_id,))
            c.execute("DELETE FROM categories WHERE id=?", (cat_id,))
            conn.commit()
            
            # Select another category
            if self.selected_category_id == cat_id:
                self.selected_category_id = None
                
            self.load_categories()
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"حدث خطأ أثناء حذف القسم: {str(e)}")
        finally:
            conn.close()

    def load_category_items(self):
        # Clear items layout
        for i in reversed(range(self.items_layout.count())):
            item = self.items_layout.itemAt(i)
            if item.widget():
                item.widget().setParent(None)
                
        if not self.selected_category_id:
            self.lbl_items_title.setText("🍔 لا يوجد قسم محدد")
            self.add_prod_frame.setEnabled(False)
            placeholder = QLabel("الرجاء إضافة قسم أو اختيار قسم من القائمة اليمنى لعرض أصنافه.", self.items_container)
            placeholder.setStyleSheet("color: #6b7280; font-style: italic; padding: 20px; text-align: center;")
            self.items_layout.addWidget(placeholder)
            return
            
        self.add_prod_frame.setEnabled(True)
        
        conn = database.get_connection()
        c = conn.cursor()
        
        # Get category name
        c.execute("SELECT name FROM categories WHERE id=?", (self.selected_category_id,))
        cat_row = c.fetchone()
        cat_name = pos_text(cat_row[0]) if cat_row else ""
        self.lbl_items_title.setText(f"🍔 الأصناف التابعة لقسم: {cat_name}")
        
        # Get products
        c.execute("SELECT id, name, base_price, is_available FROM menu_items WHERE category_id=?", (self.selected_category_id,))
        items = c.fetchall()
        conn.close()
        
        for item_id, name, price, available in items:
            display_name = pos_text(name) or "صنف"
            row = QFrame(self.items_container)
            row.setStyleSheet("background: #ffffff; border: 1px solid #e5e7eb; border-radius: 6px; padding: 6px;")
            r_layout = QHBoxLayout(row)
            r_layout.setContentsMargins(6, 6, 6, 6)
            r_layout.setSpacing(8)
            
            lbl_name = QLabel(display_name, row)
            lbl_name.setStyleSheet("font-weight: bold; font-size: 13px; color: #111827;")
            r_layout.addWidget(lbl_name, stretch=2)
            
            # Price input
            lbl_prc = QLabel("السعر:", row)
            lbl_prc.setStyleSheet("color: #4b5563; font-size: 11px;")
            r_layout.addWidget(lbl_prc)
            
            price_input = QLineEdit(str(price), row)
            price_input.setFixedWidth(70)
            price_input.setFixedHeight(28)
            price_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
            price_input.setStyleSheet("QLineEdit { background: #ffffff; border: 1px solid #d1d5db; border-radius: 4px; color: #111827; padding: 2px; font-weight: bold; } QLineEdit:focus { border-color: #0078d4; }")
            price_input.editingFinished.connect(lambda p_inp=price_input, idx=item_id: self.update_price(idx, p_inp.text()))
            r_layout.addWidget(price_input)
            
            # Availability button
            btn_stock = QPushButton("متوفر نشط" if available else "غير متوفر (خلصان)", row)
            btn_stock.setFixedHeight(28)
            btn_stock.setProperty("item_id", item_id)
            btn_stock.setProperty("status", available)
            if available:
                btn_stock.setStyleSheet("QPushButton { background-color: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; border-radius: 6px; font-weight: bold; font-size: 11px; padding: 0 10px; } QPushButton:hover { background-color: #15803d; color: white; }")
            else:
                btn_stock.setStyleSheet("QPushButton { background-color: #fee2e2; color: #b91c1c; border: 1px solid #fca5a5; border-radius: 6px; font-weight: bold; font-size: 11px; padding: 0 10px; } QPushButton:hover { background-color: #dc2626; color: white; }")
            btn_stock.clicked.connect(lambda checked, b=btn_stock: self.toggle_availability(b))
            r_layout.addWidget(btn_stock)
            
            # Delete product button
            btn_del_prod = QPushButton("🗑️", row)
            btn_del_prod.setFixedSize(28, 28)
            btn_del_prod.setStyleSheet("QPushButton { background: #fde7e9; color: #a80000; border: 1px solid #fbc4c4; border-radius: 6px; } QPushButton:hover { background: #e81123; color: white; }")
            btn_del_prod.clicked.connect(lambda checked, idx=item_id, n=display_name: self.delete_product_action(idx, n))
            r_layout.addWidget(btn_del_prod)
            
            self.items_layout.addWidget(row)
            
        self.items_layout.addStretch()

    def update_price(self, item_id, price_str):
        try:
            price = float(price_str)
            conn = database.get_connection()
            c = conn.cursor()
            c.execute("UPDATE menu_items SET base_price=? WHERE id=?", (price, item_id))
            conn.commit()
            conn.close()
        except ValueError:
            pass

    def toggle_availability(self, btn):
        item_id = btn.property("item_id")
        current_status = btn.property("status")
        new_status = 0 if current_status == 1 else 1
        
        conn = database.get_connection()
        c = conn.cursor()
        c.execute("UPDATE menu_items SET is_available=? WHERE id=?", (new_status, item_id))
        conn.commit()
        conn.close()
        
        btn.setProperty("status", new_status)
        if new_status == 1:
            btn.setText("متوفر نشط")
            btn.setStyleSheet("QPushButton { background-color: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; border-radius: 6px; font-weight: bold; font-size: 11px; padding: 0 10px; } QPushButton:hover { background-color: #15803d; color: white; }")
        else:
            btn.setText("غير متوفر (خلصان)")
            btn.setStyleSheet("QPushButton { background-color: #fee2e2; color: #b91c1c; border: 1px solid #fca5a5; border-radius: 6px; font-weight: bold; font-size: 11px; padding: 0 10px; } QPushButton:hover { background-color: #dc2626; color: white; }")

    def add_product_action(self):
        name = self.txt_new_prod_name.text().strip()
        price_str = self.txt_new_prod_price.text().strip()
        
        if not name:
            QMessageBox.warning(self, "خطأ", "برجاء كتابة اسم الصنف الجديد.")
            return
            
        try:
            price = float(price_str)
        except ValueError:
            QMessageBox.warning(self, "خطأ", "برجاء إدخال قيمة سعر صالحة.")
            return
            
        if not self.selected_category_id:
            QMessageBox.warning(self, "خطأ", "لا يوجد قسم محدد لإضافة الصنف إليه.")
            return
            
        conn = database.get_connection()
        c = conn.cursor()
        try:
            c.execute("INSERT INTO menu_items (category_id, name, base_price, is_available) VALUES (?, ?, ?, 1)", (self.selected_category_id, name, price))
            conn.commit()
            self.txt_new_prod_name.clear()
            self.txt_new_prod_price.clear()
            self.load_category_items()
        except sqlite3.IntegrityError:
            QMessageBox.critical(self, "خطأ", "اسم هذا الصنف موجود بالفعل بالسيستم.")
        finally:
            conn.close()

    def delete_product_action(self, item_id, name):
        confirm = QMessageBox.question(
            self, "حذف الصنف",
            f"هل أنت متأكد من حذف الصنف '{name}' نهائياً من المنيو؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
            
        conn = database.get_connection()
        c = conn.cursor()
        try:
            c.execute("DELETE FROM menu_items WHERE id=?", (item_id,))
            conn.commit()
            self.load_category_items()
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"حدث خطأ أثناء حذف الصنف: {str(e)}")
        finally:
            conn.close()
