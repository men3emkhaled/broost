# -*- coding: utf-8 -*-
"""Broost POS - Custom Window Title Bar"""
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtGui import QMouseEvent, QFont


class CustomTitleBar(QWidget):
    """Custom titlebar for the frameless PyQt application window."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.setObjectName("TitleBar")
        self.setFixedHeight(38)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        
        # Window controls (Close, Maximize, Minimize) on left for RTL Arabic
        self.controls_layout = QHBoxLayout()
        self.controls_layout.setSpacing(2)
        
        self.btn_close = QPushButton("✕", self)
        self.btn_close.setObjectName("WindowControlBtn")
        self.btn_close.setFixedSize(30, 26)
        self.btn_close.setStyleSheet("QPushButton { background: transparent; border: none; color: #ff8e8e; font-weight: bold; } QPushButton:hover { background: #ef4444; color: white; }")
        self.btn_close.clicked.connect(self.close_window)
        
        self.btn_maximize = QPushButton("▢", self)
        self.btn_maximize.setObjectName("WindowControlBtn")
        self.btn_maximize.setFixedSize(30, 26)
        self.btn_maximize.setStyleSheet("QPushButton { background: transparent; border: none; color: #555555; } QPushButton:hover { background: #e5e5e5; }")
        self.btn_maximize.clicked.connect(self.maximize_window)
        
        self.btn_minimize = QPushButton("—", self)
        self.btn_minimize.setObjectName("WindowControlBtn")
        self.btn_minimize.setFixedSize(30, 26)
        self.btn_minimize.setStyleSheet("QPushButton { background: transparent; border: none; color: #555555; } QPushButton:hover { background: #e5e5e5; }")
        self.btn_minimize.clicked.connect(self.minimize_window)

        
        self.controls_layout.addWidget(self.btn_close)
        self.controls_layout.addWidget(self.btn_maximize)
        self.controls_layout.addWidget(self.btn_minimize)
        
        layout.addLayout(self.controls_layout)
        layout.addStretch()
        
        # App Title on right (Arabic RTL)
        self.title_label = QLabel("نظام مبيعات الكاشير والدليفري v1.0.0", self)
        self.title_label.setObjectName("TitleLabel")
        layout.addWidget(self.title_label)
        
        self.drag_position = QPoint()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.parent.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.parent.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def close_window(self):
        self.parent.close()

    def maximize_window(self):
        if self.parent.isMaximized():
            self.parent.showNormal()
        else:
            self.parent.showMaximized()

    def minimize_window(self):
        self.parent.showMinimized()
