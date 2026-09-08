import json
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import tempfile
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import patch,MagicMock
from urllib.error import HTTPError,URLError
import ssl

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication
from core import config
from core.cloud_diagnostics import check_connection, connection_fingerprint, safe_report, request_json
from core.cloud_setup import SetupWizard,setup_required

DEFAULTS={'server_url':'https://example.invalid','sync_key':'never-export-device-key'}


class ConnectionCheckTests(unittest.TestCase):
    def response(self,**kwargs):
        return {'status':'ok','cloud_only':True,'menu_items':42,
                'time':datetime.now(timezone.utc).isoformat(),**kwargs}

    def check(self,result):
        with patch('core.cloud_diagnostics.request_json',side_effect=[{'status':'ok'},{'token':'private-token'},result]) as api:
            data=check_connection(DEFAULTS,'private-pin')
        self.assertEqual([c.args[1] for c in api.call_args_list],['/health','/api/pos/login','/api/pos/diagnostics'])
        return data

    def test_success_and_failure_do_not_export_credentials(self):
        result=self.check(self.response())
        self.assertTrue(result['ok'])
        report=json.dumps(safe_report([],result,False,80))
        for secret in ('private-token','private-pin',DEFAULTS['sync_key']):self.assertNotIn(secret,report)
        for error in (HTTPError('https://private-pin',401,'private-token',{},None),URLError(ssl.SSLError('private-pin'))):
            with patch('core.cloud_diagnostics.request_json',side_effect=error):
                failed=check_connection(DEFAULTS,'private-pin')
            self.assertFalse(failed['ok']);self.assertNotIn('private-pin',json.dumps(failed))

    def test_old_server_empty_menu_and_bad_clock_block_readiness(self):
        for result in (self.response(cloud_only=False),self.response(menu_items=0),
                       self.response(time=(datetime.now(timezone.utc)-timedelta(hours=2)).isoformat())):
            self.assertFalse(self.check(result)['ok'])

    def test_insecure_remote_url_rejected_before_sending_credentials(self):
        with self.assertRaises(ValueError):request_json('http://example.invalid','/health')


class SetupWizardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.settings=QSettings(str(Path(self.temp.name)/'device.ini'),QSettings.Format.IniFormat)
        self.settings.setValue('terminal','original-terminal')
        self.wizard=SetupWizard(self.settings,DEFAULTS,self.temp.name)
        self.wizard.device_page.set_ready(True)
        self.wizard.connection={'ok':True,'message':'connected'}
        self.wizard.connection_page.set_ready(True)
        self.wizard.printers.clear();self.wizard.printers.addItem('Test thermal')

    def tearDown(self):
        self.wizard.close();self.wizard.deleteLater();self.app.processEvents()
        self.temp.cleanup()

    def confirm_print(self):
        with patch('core.printing.print_text_to_printer',return_value=True):self.wizard.send_test_print()
        self.wizard.print_confirmed.setChecked(True)

    def test_cannot_finish_without_physical_confirmation(self):
        self.wizard.accept();self.assertTrue(setup_required(self.settings,DEFAULTS))
        with patch('core.printing.print_text_to_printer',return_value=True):self.wizard.send_test_print()
        self.wizard.accept();self.assertTrue(setup_required(self.settings,DEFAULTS))
        self.wizard.print_confirmed.setChecked(True);self.wizard.accept()
        self.assertFalse(setup_required(self.settings,DEFAULTS))
        self.assertEqual(self.settings.value('terminal'),'original-terminal')

    def test_changing_print_settings_invalidates_confirmation(self):
        self.confirm_print();self.assertTrue(self.wizard.printer_page.isComplete())
        self.wizard.paper.setCurrentIndex(1-self.wizard.paper.currentIndex())
        self.assertFalse(self.wizard.printer_page.isComplete())
        self.wizard.accept();self.assertTrue(setup_required(self.settings,DEFAULTS))

    def test_failed_print_cannot_be_confirmed_and_cancel_does_not_change_settings(self):
        original=config.SELECTED_PRINTER
        with patch('core.printing.print_text_to_printer',return_value=False):self.wizard.send_test_print()
        self.assertFalse(self.wizard.print_confirmed.isEnabled())
        self.assertEqual(config.SELECTED_PRINTER,original)
        self.wizard.reject();self.assertEqual(self.settings.value('printer',''),'')

    def test_restart_preserves_setup_and_key_rotation_requires_recheck(self):
        self.confirm_print();self.wizard.accept()
        restarted=QSettings(self.settings.fileName(),QSettings.Format.IniFormat)
        self.assertFalse(setup_required(restarted,DEFAULTS))
        self.assertTrue(setup_required(restarted,{**DEFAULTS,'sync_key':'rotated'}))
        contents=Path(self.settings.fileName()).read_text()
        self.assertNotIn(DEFAULTS['sync_key'],contents)

    def test_missing_selected_printer_never_falls_back_to_another(self):
        from core.printing import _find_physical_printer
        with patch('PyQt6.QtPrintSupport.QPrinterInfo.availablePrinters',return_value=[]),patch('PyQt6.QtPrintSupport.QPrinterInfo.defaultPrinter') as default:
            self.assertIsNone(_find_physical_printer('Restaurant thermal'))
            default.assert_not_called()
