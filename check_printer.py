import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtPrintSupport import QPrinterInfo, QPrinter

app = QApplication(sys.argv)

print("=== AVAILABLE PRINTERS ===")
printers = QPrinterInfo.availablePrinters()
for p in printers:
    print(f"Name: {p.printerName()}")
    print(f"  Is Default: {p.isDefault()}")
    print(f"  Default Page Size: {p.defaultPageSize().name()} ({p.defaultPageSize().id()})")
    print(f"  Supported Page Sizes:")
    for sz in p.supportedPageSizes():
        print(f"    - {sz.name()} (ID: {sz.id()}, Size: {sz.size(QPrinter.Unit.Millimeter)} mm)")
    print(f"  Supported Resolutions: {p.supportedResolutions()}")
    print("-" * 40)
