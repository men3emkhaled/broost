# -*- coding: utf-8 -*-
"""Broost POS - Thermal Printer Utilities"""
from PyQt6.QtWidgets import QMessageBox
import ctypes
import html
import os


def _write_raw_receipt(printer_name: str, payload: bytes) -> None:
    """Send ESC/POS bytes to the Windows spooler without a Python extension."""
    if os.name != "nt":
        raise OSError("Raw receipt printing requires Windows")

    from ctypes import wintypes

    class DocInfo(ctypes.Structure):
        _fields_ = [
            ("pDocName", wintypes.LPWSTR),
            ("pOutputFile", wintypes.LPWSTR),
            ("pDatatype", wintypes.LPWSTR),
        ]

    spooler = ctypes.WinDLL("winspool.drv", use_last_error=True)
    spooler.OpenPrinterW.argtypes = [wintypes.LPWSTR, ctypes.POINTER(wintypes.HANDLE), ctypes.c_void_p]
    spooler.OpenPrinterW.restype = wintypes.BOOL
    spooler.StartDocPrinterW.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(DocInfo)]
    spooler.StartDocPrinterW.restype = wintypes.DWORD
    spooler.StartPagePrinter.argtypes = [wintypes.HANDLE]
    spooler.StartPagePrinter.restype = wintypes.BOOL
    spooler.WritePrinter.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                                     ctypes.POINTER(wintypes.DWORD)]
    spooler.WritePrinter.restype = wintypes.BOOL
    spooler.EndPagePrinter.argtypes = [wintypes.HANDLE]
    spooler.EndPagePrinter.restype = wintypes.BOOL
    spooler.EndDocPrinter.argtypes = [wintypes.HANDLE]
    spooler.EndDocPrinter.restype = wintypes.BOOL
    spooler.ClosePrinter.argtypes = [wintypes.HANDLE]
    spooler.ClosePrinter.restype = wintypes.BOOL

    def checked(result):
        if not result:
            raise ctypes.WinError(ctypes.get_last_error())
        return result

    handle = wintypes.HANDLE()
    checked(spooler.OpenPrinterW(printer_name, ctypes.byref(handle), None))
    doc_started = False
    page_started = False
    try:
        doc_info = DocInfo("Broost POS Receipt", None, "RAW")
        checked(spooler.StartDocPrinterW(handle, 1, ctypes.byref(doc_info)))
        doc_started = True
        checked(spooler.StartPagePrinter(handle))
        page_started = True
        buffer = ctypes.create_string_buffer(payload)
        written = wintypes.DWORD()
        checked(spooler.WritePrinter(handle, buffer, len(payload), ctypes.byref(written)))
        if written.value != len(payload):
            raise IOError(f"Printer accepted {written.value} of {len(payload)} bytes")
    finally:
        if page_started:
            spooler.EndPagePrinter(handle)
        if doc_started:
            spooler.EndDocPrinter(handle)
        spooler.ClosePrinter(handle)

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
        # A missing configured printer must not silently route receipts elsewhere.
        return None

    # 2. Check if default printer is physical
    default_p = QPrinterInfo.defaultPrinter()
    if not default_p.isNull() and not is_virtual_printer(default_p):
        return default_p

    # 3. Search all available printers for a physical one
    available = QPrinterInfo.availablePrinters()
    physical_printers = [p for p in available if not is_virtual_printer(p)]

    if not physical_printers:
        return None

    # Prefer Rongta RP-350 and other thermal/POS printers by name
    thermal_keywords = [
        "rp350", "rp-350", "rongta", "rongeta", "rp326", "rp327", "rp330", "rp80",
        "pos", "thermal", "xp-", "receipt", "gp-", "sprt", "zjiang", "epson", "citizen", "star", "xprinter", "80mm", "pos-80"
    ]
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
        font_scale = getattr(config, "PRINT_FONT_SCALE", 1.0)
        if font_scale not in (1.0, 1.2):
            font_scale = 1.0
        printable_width_px = (printable_width_mm * logical_dpi) / 25.4

        doc = QTextDocument()
        doc.setDocumentMargin(0)
        doc.setTextWidth(printable_width_px / font_scale)

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
        physical_height_px = max(1, int(math.ceil((content_height_px * physical_dpi * font_scale) / logical_dpi)))

        image = QImage(physical_width_px, physical_height_px, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        painter.scale(physical_dpi * font_scale / logical_dpi, physical_dpi * font_scale / logical_dpi)
        doc.drawContents(painter)
        painter.end()

        mono_img = image.convertToFormat(QImage.Format.Format_Mono, Qt.ImageConversionFlag.ThresholdDither)
        width_bytes = physical_width_px // 8
        bytes_per_line = mono_img.bytesPerLine()
        ptr = mono_img.bits()
        ptr.setsize(mono_img.sizeInBytes())
        raw_bytes = bytes(ptr)

        # Trim trailing blank lines to avoid paper waste (stops receipt from being too long)
        last_non_empty_y = physical_height_px - 1
        while last_non_empty_y > 0:
            start = last_non_empty_y * bytes_per_line
            if any(raw_bytes[start:start + width_bytes]):
                break
            last_non_empty_y -= 1

        # Tiny safety breathing margin below content (8 dots ~ 1mm)
        trimmed_height_px = min(physical_height_px, last_non_empty_y + 8)

        # Build ESC/POS payload optimized for Rongta RP350 80mm
        escpos_data = bytearray(b'\x1b\x40')  # ESC @ (Initialize printer)

        # Kick RJ-11 cash drawer on customer/cashier receipts (ESC p 0 25 250)
        is_kitchen = ("مطبخ" in text_content) or ("نسخة المطبخ" in text_content)
        if not is_kitchen:
            escpos_data.extend(b'\x1b\x70\x00\x19\xfa')

        # GS v 0 (Raster bit image mode)
        escpos_data.extend(b'\x1d\x76\x30\x00')
        escpos_data.append(width_bytes % 256)
        escpos_data.append(width_bytes // 256)
        escpos_data.append(trimmed_height_px % 256)
        escpos_data.append(trimmed_height_px // 256)
        for y in range(trimmed_height_px):
            start = y * bytes_per_line
            escpos_data.extend(raw_bytes[start:start + width_bytes])

        # Feed minimal paper before cutter: 2 lines instead of 4 (Rongta RP350 cutter is close to thermal head)
        escpos_data.extend(b'\x1b\x64\x02')
        # Partial cut (GS V 1)
        escpos_data.extend(b'\x1d\x56\x01')

        _write_raw_receipt(printer_name, bytes(escpos_data))

        return True
    except Exception as e:
        if parent:
            QMessageBox.critical(parent, "خطأ بالطباعة", f"حدث خطأ أثناء إرسال الفاتورة للطابعة:\n{str(e)}")
        return False
