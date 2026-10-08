"""Check the Windows spooler call sequence without sending a real print job."""

import ctypes
import os
import unittest
from ctypes import wintypes
from types import SimpleNamespace
from unittest.mock import patch

from core.printing import _write_raw_receipt


class FakeFunction:
    def __init__(self, callback):
        self.callback = callback

    def __call__(self, *args):
        return self.callback(*args)


@unittest.skipUnless(os.name == "nt", "Windows spooler only")
class SpoolerTests(unittest.TestCase):
    def test_raw_bytes_are_written_and_handles_closed(self):
        events = []
        payload = b"\x1b@\x1dv0\x00\x01\x02"

        def record(name, result=1):
            def callback(*_args):
                events.append(name)
                return result
            return FakeFunction(callback)

        def write(_handle, buffer, length, written):
            events.append("write")
            self.assertEqual(ctypes.string_at(buffer, length), payload)
            ctypes.cast(written, ctypes.POINTER(wintypes.DWORD)).contents.value = length
            return 1

        spooler = SimpleNamespace(
            OpenPrinterW=record("open"),
            StartDocPrinterW=record("start_doc"),
            StartPagePrinter=record("start_page"),
            WritePrinter=FakeFunction(write),
            EndPagePrinter=record("end_page"),
            EndDocPrinter=record("end_doc"),
            ClosePrinter=record("close"),
        )
        with patch.object(ctypes, "WinDLL", return_value=spooler):
            _write_raw_receipt("Test Printer", payload)
        self.assertEqual(events, [
            "open", "start_doc", "start_page", "write",
            "end_page", "end_doc", "close",
        ])


if __name__ == "__main__":
    unittest.main()
