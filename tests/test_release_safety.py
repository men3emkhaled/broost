import tempfile
import unittest
from pathlib import Path
from scripts.build_windows_release import fresh_release_directory


class ReleaseSafetyTests(unittest.TestCase):
    def test_existing_release_and_its_database_cannot_be_reused(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = fresh_release_directory(root, 'release_test')
            database = output / 'broost_pos.db'
            database.write_bytes(b'existing cashier data')
            with self.assertRaises(FileExistsError):
                fresh_release_directory(root, 'release_test')
            self.assertEqual(database.read_bytes(), b'existing cashier data')

    def test_build_refuses_live_installation_and_paths_outside_workspace(self):
        with tempfile.TemporaryDirectory() as temp:
            for name in ('dist', 'dist/BroostPOS', '../release_outside'):
                with self.assertRaises(ValueError):
                    fresh_release_directory(Path(temp), name)
