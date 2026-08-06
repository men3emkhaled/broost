# -*- coding: utf-8 -*-
"""Large cashier alert for incoming website orders."""

from __future__ import annotations

import os

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from core.display_text import pos_text


class OnlineOrderAlertDialog(QDialog):
    """Blocking, centered alert that remains until the cashier chooses an action."""

    def __init__(self, order: dict, parent=None):
        super().__init__(parent)
        self.order = order
        self.action = ""
        self.setWindowTitle("طلب أونلاين جديد")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setModal(True)
        self.setMinimumSize(700, 520)
        self.setMaximumSize(960, 760)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setObjectName("OnlineOrderAlert")
        self._build_ui()

        self.sound_timer = QTimer(self)
        self.sound_timer.timeout.connect(self._play_alert_sound)
        self.sound_timer.start(3500)
        QTimer.singleShot(150, self._play_alert_sound)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        header = QFrame(self)
        header.setObjectName("OnlineAlertHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 16, 18, 16)
        header_layout.setSpacing(14)

        icon = QLabel("🔔", header)
        icon.setObjectName("OnlineAlertIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setFixedSize(58, 58)
        header_layout.addWidget(icon)

        title_box = QVBoxLayout()
        title = QLabel(f"أوردر أونلاين جديد  {self.order.get('public_number', '')}", header)
        title.setObjectName("OnlineAlertTitle")
        title_box.addWidget(title)
        subtitle = QLabel(self._subtitle(), header)
        subtitle.setObjectName("OnlineAlertSubtitle")
        title_box.addWidget(subtitle)
        header_layout.addLayout(title_box, stretch=1)

        total = QLabel(f"{float(self.order.get('total', 0)):,.2f} ج.م", header)
        total.setObjectName("OnlineAlertTotal")
        header_layout.addWidget(total)
        root.addWidget(header)

        reliability = self.order.get("customer_reliability") or {}
        order_mood = reliability.get("order_mood", "NEUTRAL")
        mood_styles = {
            "HAPPY": ("🙂", "استلم آخر طلب وكل شيء تمام", "#166534", "#dcfce7", "#22c55e"),
            "NEUTRAL": ("😐", "أول طلب للعميل", "#4b5563", "#f3f4f6", "#9ca3af"),
            "ANGRY": ("😠", "طلب سابق رجع أو لم يُستلم", "#991b1b", "#fee2e2", "#ef4444"),
        }
        mood_emoji, trust_label, trust_color, trust_bg, mood_badge_bg = mood_styles.get(
            order_mood, mood_styles["NEUTRAL"]
        )
        trust_frame = QFrame(self)
        trust_frame.setStyleSheet(
            f"QFrame {{ background: {trust_bg}; border: 1px solid {trust_color}; "
            "border-radius: 9px; }} QLabel { border: none; background: transparent; }"
        )
        trust_layout = QHBoxLayout(trust_frame)
        trust_layout.setContentsMargins(14, 9, 14, 9)
        mood_badge = QLabel(mood_emoji, trust_frame)
        mood_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mood_badge.setFixedSize(42, 42)
        mood_badge.setStyleSheet(
            f"background: {mood_badge_bg}; border: 2px solid {trust_color}; "
            "border-radius: 21px; font-size: 23px;"
        )
        trust_layout.addWidget(mood_badge)
        trust_title = QLabel(trust_label, trust_frame)
        trust_title.setStyleSheet(f"color: {trust_color}; font-size: 14px; font-weight: 900;")
        trust_layout.addWidget(trust_title)
        trust_layout.addStretch()
        trust_facts = QLabel(
            f"{int(reliability.get('completed_orders', 0) or 0)} طلب مستلم  •  "
            f"{int(reliability.get('cancelled_orders', 0) or 0)} طلب ملغي أو راجع",
            trust_frame,
        )
        trust_facts.setStyleSheet(f"color: {trust_color}; font-size: 12px; font-weight: 700;")
        trust_layout.addWidget(trust_facts)
        root.addWidget(trust_frame)

        content = QHBoxLayout()
        content.setSpacing(16)

        details = QFrame(self)
        details.setObjectName("OnlineAlertDetails")
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(18, 18, 18, 18)
        details_layout.setSpacing(8)
        rows = [
            ("العميل", self.order.get("customer_name") or "—"),
            ("الموبايل", self.order.get("customer_phone") or "—"),
            ("الاستلام", "دليفري" if self.order.get("fulfillment") == "DELIVERY" else "استلام من المطعم"),
        ]
        if self.order.get("fulfillment") == "DELIVERY":
            rows.extend([
                ("القرية", self.order.get("area_name") or "—"),
                ("العنوان", self.order.get("detailed_address") or "—"),
            ])
        rows.extend([
            ("طريقة الدفع", "محفظة" if self.order.get("payment_method") == "WALLET" else "نقدي"),
            ("حالة الدفع", self._payment_status_label()),
            ("قيمة المنتجات", f"{float(self.order.get('subtotal', 0)):,.2f} ج.م"),
            ("رسوم التوصيل", f"{float(self.order.get('delivery_fee', 0)):,.2f} ج.م"),
        ])
        for label, value in rows:
            row = QHBoxLayout()
            row_label = QLabel(label, details)
            row_label.setObjectName("OnlineAlertRowLabel")
            row.addWidget(row_label)
            row.addStretch()
            row_value = QLabel(str(value), details)
            row_value.setObjectName("OnlineAlertRowValue")
            row_value.setWordWrap(True)
            row_value.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(row_value, stretch=2)
            details_layout.addLayout(row)
        details_layout.addStretch()
        content.addWidget(details, stretch=1)

        items_frame = QFrame(self)
        items_frame.setObjectName("OnlineAlertItems")
        items_layout = QVBoxLayout(items_frame)
        items_layout.setContentsMargins(18, 18, 18, 18)
        items_layout.setSpacing(8)
        items_title = QLabel("محتويات الطلب", items_frame)
        items_title.setObjectName("OnlineAlertSectionTitle")
        items_layout.addWidget(items_title)

        scroll = QScrollArea(items_frame)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget(scroll)
        list_layout = QVBoxLayout(container)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(7)
        for item in self.order.get("items", []):
            extras = item.get("extras", [])
            extra_names = "، ".join(
                filter(None, (pos_text(extra.get("name", "")) for extra in extras))
            )
            text = f"{item.get('quantity', 1)} × {pos_text(item.get('item_name')) or 'صنف'}"
            if item.get("size_name") and item.get("size_name") != "عادي":
                text += f" — {pos_text(item['size_name'])}"
            if extra_names:
                text += f"\n{extra_names}"
            item_label = QLabel(text, container)
            item_label.setObjectName("OnlineAlertItem")
            item_label.setWordWrap(True)
            list_layout.addWidget(item_label)
        list_layout.addStretch()
        scroll.setWidget(container)
        items_layout.addWidget(scroll, stretch=1)

        proof_bytes = self.order.get("proof_bytes") or b""
        if proof_bytes:
            proof_title = QLabel("سكرين شوت التحويل", items_frame)
            proof_title.setObjectName("OnlineAlertSectionTitle")
            items_layout.addWidget(proof_title)
            pixmap = QPixmap()
            if pixmap.loadFromData(proof_bytes):
                proof = QLabel(items_frame)
                proof.setAlignment(Qt.AlignmentFlag.AlignCenter)
                proof.setPixmap(
                    pixmap.scaled(
                        320,
                        220,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                items_layout.addWidget(proof)
        content.addWidget(items_frame, stretch=1)
        root.addLayout(content, stretch=1)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        reject_button = QPushButton("رفض الطلب", self)
        reject_button.setObjectName("OnlineRejectButton")
        reject_button.setMinimumHeight(48)
        reject_button.clicked.connect(self._reject_order)
        actions.addWidget(reject_button)

        self.primary_button = QPushButton(self._primary_label(), self)
        self.primary_button.setObjectName("OnlineAcceptButton")
        self.primary_button.setMinimumHeight(48)
        self.primary_button.clicked.connect(self._accept_order)
        actions.addWidget(self.primary_button, stretch=1)
        root.addLayout(actions)

    def _subtitle(self) -> str:
        fulfillment = "دليفري" if self.order.get("fulfillment") == "DELIVERY" else "استلام من المطعم"
        payment = "محفظة" if self.order.get("payment_method") == "WALLET" else "نقدي"
        return f"{fulfillment}  •  {payment}"

    def _payment_status_label(self) -> str:
        return {
            "AWAITING_PAYMENT": "بانتظار التحويل",
            "PROOF_UPLOADED": "سكرين شوت مرفوع — يحتاج مراجعة",
            "CONFIRMED": "تم تأكيد التحويل",
            "REJECTED": "إثبات التحويل مرفوض",
            "CASH_ON_DELIVERY": "نقدي عند التسليم",
            "CASH_ON_PICKUP": "نقدي عند الاستلام",
        }.get(self.order.get("payment_status"), "غير محدد")

    def _primary_label(self) -> str:
        if self.order.get("payment_method") == "WALLET":
            if self.order.get("payment_status") == "PROOF_UPLOADED":
                return "تأكيد التحويل — استلام وطباعة"
            if self.order.get("payment_status") == "CONFIRMED":
                return "استلام وطباعة"
            return "تم الاطلاع — انتظار التحويل"
        return "استلام الطلب وطباعة الفاتورة"

    def _accept_order(self) -> None:
        if self.order.get("payment_method") == "WALLET" and self.order.get("payment_status") not in (
            "PROOF_UPLOADED",
            "CONFIRMED",
        ):
            self.action = "acknowledge"
        else:
            self.action = "accept"
        self.accept()

    def _reject_order(self) -> None:
        self.action = "reject"
        self.reject()

    def _play_alert_sound(self) -> None:
        if os.name == "nt":
            try:
                import winsound

                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                return
            except Exception:
                pass
        QApplication.beep()

    def done(self, result: int) -> None:
        self.sound_timer.stop()
        super().done(result)


class CustomerCancelledOrderAlertDialog(QDialog):
    """Large alarm shown when a customer cancels an active website order."""

    def __init__(self, order: dict, parent=None):
        super().__init__(parent)
        self.order = order
        self.setWindowTitle("العميل ألغى الطلب")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setModal(True)
        self.setMinimumSize(680, 430)
        self.setMaximumSize(900, 650)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setStyleSheet("""
            QDialog { background: #fff7f7; border: 4px solid #dc2626; border-radius: 18px; }
            QLabel { border: none; background: transparent; }
            QLabel#CancelAlarmIcon { font-size: 56px; }
            QLabel#CancelAlarmTitle { color: #991b1b; font-size: 30px; font-weight: 900; }
            QLabel#CancelAlarmNumber { color: #dc2626; font-size: 24px; font-weight: 900; }
            QLabel#CancelAlarmDetails { color: #1f2937; font-size: 18px; font-weight: 800; }
            QLabel#CancelAlarmWarning {
                color: #7f1d1d; background: #fee2e2; border: 2px solid #f87171;
                border-radius: 12px; padding: 16px; font-size: 19px; font-weight: 900;
            }
            QPushButton {
                color: white; background: #b91c1c; border: none; border-radius: 11px;
                min-height: 54px; padding: 8px 22px; font-size: 18px; font-weight: 900;
            }
            QPushButton:hover { background: #991b1b; }
        """)
        self._build_ui()

        self.sound_timer = QTimer(self)
        self.sound_timer.timeout.connect(self._play_alarm_sound)
        self.sound_timer.start(2500)
        QTimer.singleShot(100, self._play_alarm_sound)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 26, 30, 26)
        root.setSpacing(16)

        icon = QLabel("🚨", self)
        icon.setObjectName("CancelAlarmIcon")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(icon)

        title = QLabel("العميل ألغى الطلب", self)
        title.setObjectName("CancelAlarmTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(title)

        number = QLabel(str(self.order.get("public_number") or ""), self)
        number.setObjectName("CancelAlarmNumber")
        number.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(number)

        fulfillment = (
            "دليفري" if self.order.get("fulfillment") == "DELIVERY" else "استلام من المطعم"
        )
        details = QLabel(
            f"{self.order.get('customer_name') or 'عميل'}  •  "
            f"{self.order.get('customer_phone') or 'بدون رقم'}\n"
            f"{fulfillment}  •  الإجمالي {float(self.order.get('total', 0)):,.2f} ج.م",
            self,
        )
        details.setObjectName("CancelAlarmDetails")
        details.setAlignment(Qt.AlignmentFlag.AlignCenter)
        details.setWordWrap(True)
        root.addWidget(details)

        warning = QLabel("أوقف تجهيز الطلب وتأكد إنه ماخرجش للتوصيل.", self)
        warning.setObjectName("CancelAlarmWarning")
        warning.setAlignment(Qt.AlignmentFlag.AlignCenter)
        warning.setWordWrap(True)
        root.addWidget(warning)

        root.addStretch()
        close_button = QPushButton("تم — إغلاق التنبيه", self)
        close_button.clicked.connect(self.accept)
        root.addWidget(close_button)

    def _play_alarm_sound(self) -> None:
        if os.name == "nt":
            try:
                import winsound

                winsound.MessageBeep(winsound.MB_ICONHAND)
                return
            except Exception:
                pass
        QApplication.beep()

    def done(self, result: int) -> None:
        self.sound_timer.stop()
        super().done(result)
