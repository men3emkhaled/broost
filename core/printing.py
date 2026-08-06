# -*- coding: utf-8 -*-
"""Broost POS - Thermal Printer Utilities"""
from PyQt6.QtWidgets import QMessageBox
import html

# Virtual/file-based printers that should NEVER be used
VIRTUAL_KEYWORDS = ["pdf", "xps", "onenote", "writer", "fax", "virtual", "send to", "microsoft print"]

# Global cache for printer lookups to avoid slow OS spooler queries
_CACHED_PRINTER = None
_CACHED_PRINTER_NAME = None

def is_virtual_printer(p_obj):
    """Check if a printer is a virtual/file-saving printer (PDF, XPS, etc.)."""
    if p_obj.isNull():
        return True
    name = p_obj.printerName().lower()
    return any(kw in name for kw in VIRTUAL_KEYWORDS)

def get_physical_printer():
    """Find a real physical printer with caching. Returns QPrinterInfo or None."""
    global _CACHED_PRINTER, _CACHED_PRINTER_NAME
    from core import config

    selected_name = getattr(config, "SELECTED_PRINTER", "")
    
    # Return cached printer if available and selected name hasn't changed
    if _CACHED_PRINTER is not None and selected_name == _CACHED_PRINTER_NAME:
        if not _CACHED_PRINTER.isNull():
            return _CACHED_PRINTER

    printer = _find_physical_printer(selected_name)
    if printer is not None:
        _CACHED_PRINTER = printer
        _CACHED_PRINTER_NAME = selected_name
    return printer

def _find_physical_printer(selected_name):
    from PyQt6.QtPrintSupport import QPrinterInfo
    
    # 1. Use user-selected printer if set
    if selected_name:
        available = QPrinterInfo.availablePrinters()
        for p in available:
            if p.printerName() == selected_name and not is_virtual_printer(p):
                return p

    # 2. Check if default printer is physical
    default_p = QPrinterInfo.defaultPrinter()
    if not default_p.isNull() and not is_virtual_printer(default_p):
        return default_p

    # 3. Search all available printers for a physical one
    available = QPrinterInfo.availablePrinters()
    physical_printers = [p for p in available if not is_virtual_printer(p)]

    if not physical_printers:
        return None

    # Prefer thermal/POS printers by name
    thermal_keywords = ["pos", "thermal", "xp-", "receipt", "gp-", "sprt", "zjiang", "epson", "citizen", "star", "xprinter"]
    for p in physical_printers:
        p_name = p.printerName().lower()
        if any(tkw in p_name for tkw in thermal_keywords):
            return p

    # Return first physical printer found
    return physical_printers[0]


def print_text_to_printer(text_content, parent=None):
    try:
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QImage, QPainter, QTextDocument
        import win32print
        import math

        printer_info = get_physical_printer()

        if not printer_info:
            if parent:
                QMessageBox.critical(
                    parent, "لا توجد طابعة موصلة",
                    "لم يتم العثور على طابعة حقيقية موصلة بالجهاز.\n\n"
                    "يرجى توصيل طابعة الفواتير بالكمبيوتر وتثبيت تعريفها ثم المحاولة مرة أخرى."
                )
            return False

        printer_name = printer_info.printerName()

        from core import config
        paper_width = getattr(config, "PAPER_WIDTH", 80)

        printable_width_mm = 48.0 if paper_width == 58 else 72.0
        logical_dpi = 96.0
        printable_width_px = (printable_width_mm * logical_dpi) / 25.4

        doc = QTextDocument()
        doc.setDocumentMargin(0)
        doc.setTextWidth(printable_width_px)

        stripped = text_content.strip()
        if stripped.startswith("<html>") or stripped.startswith("<html") or stripped.startswith("<!DOCTYPE html>") or "<body" in stripped:
            formatted_html = text_content
        else:
            formatted_html = f"""
            <html><head><style>
                body {{ font-family: 'Courier New', monospace; font-size: 10pt; margin: 0; padding: 0; direction: rtl; }}
                pre {{ white-space: pre-wrap; margin: 0; }}
            </style></head><body><pre>{html.escape(text_content)}</pre></body></html>
            """
        doc.setHtml(formatted_html)

        content_height_px = doc.size().height()
        physical_dpi = 203.0
        physical_width_px = int(math.ceil((printable_width_mm * physical_dpi) / 25.4))
        physical_width_px = (physical_width_px + 7) // 8 * 8
        physical_height_px = max(1, int(math.ceil((content_height_px * physical_dpi) / logical_dpi)))

        image = QImage(physical_width_px, physical_height_px, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        painter.scale(physical_dpi / logical_dpi, physical_dpi / logical_dpi)
        doc.drawContents(painter)
        painter.end()

        mono_img = image.convertToFormat(QImage.Format.Format_Mono, Qt.ImageConversionFlag.ThresholdDither)
        width_bytes = physical_width_px // 8
        bytes_per_line = mono_img.bytesPerLine()
        ptr = mono_img.bits()
        ptr.setsize(mono_img.sizeInBytes())
        raw_bytes = bytes(ptr)

        escpos_data = bytearray(b'\x1b\x40')
        escpos_data.extend(b'\x1d\x76\x30\x00')
        escpos_data.append(width_bytes % 256)
        escpos_data.append(width_bytes // 256)
        escpos_data.append(physical_height_px % 256)
        escpos_data.append(physical_height_px // 256)
        for y in range(physical_height_px):
            start = y * bytes_per_line
            escpos_data.extend(raw_bytes[start:start + width_bytes])
        escpos_data.extend(b'\x1b\x64\x04')
        escpos_data.extend(b'\x1d\x56\x01')

        hPrinter = win32print.OpenPrinter(printer_name)
        try:
            win32print.StartDocPrinter(hPrinter, 1, ("Broost POS Receipt", None, "RAW"))
            try:
                win32print.StartPagePrinter(hPrinter)
                written = win32print.WritePrinter(hPrinter, bytes(escpos_data))
                win32print.EndPagePrinter(hPrinter)
                if written != len(escpos_data):
                    raise IOError(f"Printer accepted {written} of {len(escpos_data)} bytes")
            finally:
                win32print.EndDocPrinter(hPrinter)
        finally:
            win32print.ClosePrinter(hPrinter)

        return True
    except Exception as e:
        if parent:
            QMessageBox.critical(parent, "خطأ بالطباعة", f"حدث خطأ أثناء إرسال الفاتورة للطابعة:\n{str(e)}")
        return False
