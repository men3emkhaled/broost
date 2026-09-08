"""Localhost-only compiled smoke driver. No real printing, credentials or registry."""
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication


def drive_wizard(wizard):
    from unittest.mock import patch
    # Printing is simulated; this does not establish physical printer readiness.
    def capture(name):
        QApplication.processEvents()
        wizard.grab().save(str(wizard.settings_dir/('setup-'+name+'.png')))

    def advance():
        capture('device')
        if not wizard.device_page.isComplete():
            return
        wizard.next()
        wizard.pin.setText('isolated-test-pin')
        wizard.start_connection()
        wizard.worker.finished.connect(after_connection)

    def after_connection():
        capture('connection')
        if not wizard.connection_page.isComplete():
            return
        wizard.next()
        wizard.printers.clear(); wizard.printers.addItem('Isolated test printer')
        with patch('core.printing.print_text_to_printer',return_value=True):
            wizard.send_test_print()
        wizard.print_confirmed.setChecked(True)
        capture('printer')
        wizard.next(); capture('options'); wizard.next()
        capture('summary')
        # Do not mutate the real Windows startup registry in a packaged smoke run.
        with patch('core.cloud_setup.set_autostart'):
            wizard.accept()

    QTimer.singleShot(100,advance)
