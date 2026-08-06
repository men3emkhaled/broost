# -*- coding: utf-8 -*-
"""Create and manage discounted single-item and multi-item offers."""

import uuid

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

import database
from core.display_text import pos_text
from styles import STYLE_SHEET


class OfferEditorDialog(QDialog):
    def __init__(self, offer_id=None, parent=None):
        super().__init__(parent)
        self.offer_id = offer_id
        self._stored_offer_name = ""
        self.saved = False
        self.item_controls: dict[int, tuple[QSpinBox, float]] = {}
        self.setWindowTitle("تعديل عرض" if offer_id else "إضافة عرض")
        self.setMinimumSize(680, 720)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setStyleSheet(STYLE_SHEET)
        self._build_ui()
        if offer_id:
            self._load_offer()
        self._update_totals()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(12)

        title = QLabel("تعديل العرض" if self.offer_id else "إنشاء عرض جديد", self)
        title.setObjectName("DialogTitle")
        root.addWidget(title)

        hint = QLabel(
            "اختار صنفًا واحدًا أو أكثر وحدد الكمية. السعر الأصلي يتحسب تلقائيًا، وأنت تكتب سعر العرض فقط.",
            self,
        )
        hint.setObjectName("MutedText")
        hint.setWordWrap(True)
        root.addWidget(hint)

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        form.addWidget(QLabel("اسم العرض"), 0, 0)
        self.name_input = QLineEdit(self)
        self.name_input.setPlaceholderText("مثال: عرض البرجر المزدوج")
        form.addWidget(self.name_input, 0, 1)

        form.addWidget(QLabel("سعر العرض"), 1, 0)
        self.price_input = QDoubleSpinBox(self)
        self.price_input.setRange(0, 100000)
        self.price_input.setDecimals(2)
        self.price_input.setSuffix(" ج.م")
        self.price_input.valueChanged.connect(self._update_totals)
        form.addWidget(self.price_input, 1, 1)

        self.active_check = QCheckBox("العرض متاح للطلب الآن", self)
        self.active_check.setChecked(True)
        form.addWidget(self.active_check, 2, 1)
        root.addLayout(form)

        section = QLabel("مكونات العرض وكمياتها", self)
        section.setObjectName("OffersSectionTitle")
        root.addWidget(section)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        container = QWidget(scroll)
        listing = QVBoxLayout(container)
        listing.setContentsMargins(10, 10, 10, 10)
        listing.setSpacing(7)

        conn = database.get_connection()
        rows = conn.execute(
            """
            SELECT m.id, m.name, m.base_price, c.name
            FROM menu_items m JOIN categories c ON c.id=m.category_id
            WHERE m.is_available=1
            ORDER BY c.sort_order, c.id, m.name
            """
        ).fetchall()
        conn.close()

        current_category = None
        for item_id, item_name, base_price, category_name in rows:
            item_name = pos_text(item_name) or "صنف"
            category_name = pos_text(category_name) or "قسم"
            if category_name != current_category:
                current_category = category_name
                category = QLabel(category_name, container)
                category.setObjectName("OffersSectionTitle")
                listing.addWidget(category)

            row = QFrame(container)
            row.setObjectName("OfferChoiceRow")
            line = QHBoxLayout(row)
            line.setContentsMargins(12, 8, 12, 8)
            name = QLabel(item_name, row)
            line.addWidget(name, 1)
            price = QLabel(f"{float(base_price):.2f} ج.م", row)
            price.setObjectName("MutedText")
            line.addWidget(price)
            quantity = QSpinBox(row)
            quantity.setRange(0, 30)
            quantity.setSpecialValueText("—")
            quantity.setPrefix("الكمية: ")
            quantity.valueChanged.connect(self._update_totals)
            line.addWidget(quantity)
            self.item_controls[item_id] = (quantity, float(base_price))
            listing.addWidget(row)

        if not rows:
            empty = QLabel("لا توجد أصناف متاحة في المنيو.", container)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            listing.addWidget(empty)
        listing.addStretch()
        scroll.setWidget(container)
        root.addWidget(scroll, 1)

        totals = QFrame(self)
        totals.setObjectName("OfferChoiceRow")
        totals_layout = QHBoxLayout(totals)
        self.regular_label = QLabel("السعر الأصلي: 0.00 ج.م", totals)
        self.regular_label.setStyleSheet("font-weight: 700; color: #6b7280;")
        totals_layout.addWidget(self.regular_label)
        totals_layout.addStretch()
        self.saving_label = QLabel("التوفير: 0.00 ج.م", totals)
        self.saving_label.setStyleSheet("font-weight: 800; color: #047857;")
        totals_layout.addWidget(self.saving_label)
        root.addWidget(totals)

        actions = QHBoxLayout()
        cancel = QPushButton("إلغاء", self)
        cancel.setObjectName("BtnDark")
        cancel.clicked.connect(self.reject)
        actions.addWidget(cancel)
        save = QPushButton("حفظ ونشر العرض", self)
        save.setObjectName("BtnOffer")
        save.clicked.connect(self._save)
        actions.addWidget(save, 1)
        root.addLayout(actions)

    def _regular_price(self):
        return sum(spin.value() * price for spin, price in self.item_controls.values())

    def _update_totals(self):
        regular = self._regular_price()
        saving = max(0.0, regular - self.price_input.value())
        self.regular_label.setText(f"السعر الأصلي: {regular:.2f} ج.م")
        self.saving_label.setText(f"التوفير: {saving:.2f} ج.م")

    def _load_offer(self):
        conn = database.get_connection()
        offer = conn.execute(
            "SELECT name, offer_price, is_active FROM offers WHERE id=?", (self.offer_id,)
        ).fetchone()
        components = conn.execute(
            "SELECT menu_item_id, quantity FROM offer_items WHERE offer_id=?", (self.offer_id,)
        ).fetchall()
        conn.close()
        if not offer:
            return
        self._stored_offer_name = offer[0]
        self.name_input.setText(pos_text(offer[0]))
        self.price_input.setValue(float(offer[1]))
        self.active_check.setChecked(bool(offer[2]))
        for item_id, quantity in components:
            if item_id in self.item_controls:
                self.item_controls[item_id][0].setValue(int(quantity))

    def _save(self):
        name = self.name_input.text().strip()
        if self.offer_id and self._stored_offer_name and name == pos_text(self._stored_offer_name):
            name = self._stored_offer_name
        price = self.price_input.value()
        selected = [
            (item_id, spin.value())
            for item_id, (spin, _) in self.item_controls.items()
            if spin.value() > 0
        ]
        regular = self._regular_price()
        if not name:
            QMessageBox.warning(self, "بيانات ناقصة", "اكتب اسم العرض.")
            return
        if not selected:
            QMessageBox.warning(self, "بيانات ناقصة", "اختار مكوّنًا واحدًا على الأقل للعرض.")
            return
        if price >= regular:
            QMessageBox.warning(self, "سعر غير صحيح", "سعر العرض لازم يكون أقل من السعر الأصلي.")
            return

        conn = database.get_connection()
        try:
            if self.offer_id:
                conn.execute(
                    "UPDATE offers SET name=?, offer_price=?, is_active=? WHERE id=?",
                    (name, price, int(self.active_check.isChecked()), self.offer_id),
                )
                conn.execute("DELETE FROM offer_items WHERE offer_id=?", (self.offer_id,))
            else:
                cursor = conn.execute(
                    "INSERT INTO offers (sync_id, name, offer_price, is_active) VALUES (?, ?, ?, ?)",
                    (f"offer-{uuid.uuid4().hex}", name, price, int(self.active_check.isChecked())),
                )
                self.offer_id = cursor.lastrowid
            conn.executemany(
                "INSERT INTO offer_items (sync_id, offer_id, menu_item_id, quantity) VALUES (?, ?, ?, ?)",
                [
                    (f"offer-item-{uuid.uuid4().hex}", self.offer_id, item_id, quantity)
                    for item_id, quantity in selected
                ],
            )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            QMessageBox.critical(self, "تعذر الحفظ", f"لم يتم حفظ العرض: {exc}")
            return
        finally:
            conn.close()
        self.saved = True
        self.accept()


class DailyOffersDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.saved = False
        self.setWindowTitle("إدارة العروض")
        self.setMinimumSize(720, 650)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setStyleSheet(STYLE_SHEET)
        self._build_ui()
        self._load_offers()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(12)
        header = QHBoxLayout()
        title = QLabel("العروض والباقات", self)
        title.setObjectName("DialogTitle")
        header.addWidget(title)
        header.addStretch()
        add = QPushButton("+ إضافة عرض", self)
        add.setObjectName("BtnOffer")
        add.clicked.connect(self._add_offer)
        header.addWidget(add)
        root.addLayout(header)
        subtitle = QLabel(
            "اعمل خصم لصنف واحد، كمية من نفس الصنف، أو باكدج من أصناف مختلفة.", self
        )
        subtitle.setObjectName("MutedText")
        root.addWidget(subtitle)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        root.addWidget(self.scroll, 1)
        close = QPushButton("تم", self)
        close.setObjectName("BtnDark")
        close.clicked.connect(self.accept)
        root.addWidget(close)

    def _load_offers(self):
        container = QWidget(self.scroll)
        listing = QVBoxLayout(container)
        listing.setContentsMargins(10, 10, 10, 10)
        listing.setSpacing(9)
        conn = database.get_connection()
        rows = conn.execute(
            "SELECT id, name, offer_price, is_active FROM offers ORDER BY id DESC"
        ).fetchall()
        for offer_id, name, offer_price, is_active in rows:
            components = conn.execute(
                """
                SELECT oi.quantity, m.name, m.base_price
                FROM offer_items oi JOIN menu_items m ON m.id=oi.menu_item_id
                WHERE oi.offer_id=? ORDER BY oi.id
                """,
                (offer_id,),
            ).fetchall()
            regular = sum(int(qty) * float(price) for qty, _, price in components)
            summary = " + ".join(
                f"{int(qty)}× {pos_text(item_name) or 'صنف'}"
                for qty, item_name, _ in components
            )
            card = QFrame(container)
            card.setObjectName("OfferChoiceRow")
            line = QHBoxLayout(card)
            info = QVBoxLayout()
            name_label = QLabel(
                f"{pos_text(name) or 'عرض'}  {'● متاح' if is_active else '○ متوقف'}", card
            )
            name_label.setStyleSheet("font-size: 15px; font-weight: 800;")
            info.addWidget(name_label)
            component_label = QLabel(summary or "بدون مكونات", card)
            component_label.setObjectName("MutedText")
            component_label.setWordWrap(True)
            info.addWidget(component_label)
            price_label = QLabel(f"بدل {regular:.2f} ج.م  ←  {float(offer_price):.2f} ج.م", card)
            price_label.setStyleSheet("font-weight: 800; color: #047857;")
            info.addWidget(price_label)
            line.addLayout(info, 1)
            edit = QPushButton("تعديل", card)
            edit.clicked.connect(lambda checked=False, oid=offer_id: self._edit_offer(oid))
            line.addWidget(edit)
            delete = QPushButton("حذف", card)
            delete.setObjectName("BtnDanger")
            delete.clicked.connect(lambda checked=False, oid=offer_id: self._delete_offer(oid))
            line.addWidget(delete)
            listing.addWidget(card)
        conn.close()
        if not rows:
            empty = QLabel("لسه مفيش عروض. اضغط «إضافة عرض» وابدأ.", container)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setObjectName("MutedText")
            listing.addWidget(empty)
        listing.addStretch()
        self.scroll.setWidget(container)

    def _add_offer(self):
        dialog = OfferEditorDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.saved:
            self.saved = True
            self._load_offers()

    def _edit_offer(self, offer_id):
        dialog = OfferEditorDialog(offer_id, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.saved:
            self.saved = True
            self._load_offers()

    def _delete_offer(self, offer_id):
        answer = QMessageBox.question(
            self, "حذف العرض", "تمسح العرض نهائيًا؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        conn = database.get_connection()
        conn.execute("DELETE FROM offer_items WHERE offer_id=?", (offer_id,))
        conn.execute("DELETE FROM offers WHERE id=?", (offer_id,))
        conn.commit()
        conn.close()
        self.saved = True
        self._load_offers()
