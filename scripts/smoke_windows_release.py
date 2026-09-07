"""Start a packaged POS against an isolated local database, never restaurant data."""

import argparse
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--app-dir', required=True, type=Path)
    args = parser.parse_args()
    source = args.app_dir.resolve()
    if not (source / 'BroostPOS.exe').is_file():
        raise SystemExit('Missing packaged BroostPOS.exe')
    with tempfile.TemporaryDirectory(prefix='broost-package-smoke-') as temp:
        target = Path(temp)
        shutil.copytree(source / '_internal', target / '_internal')
        shutil.copy2(source / 'BroostPOS.exe', target / 'BroostPOS.exe')
        # No local web-server executable is copied. Disable every production
        # connection before startup, including when a production key is bundled.
        env = os.environ.copy()
        env.update(QT_QPA_PLATFORM='offscreen', BROOST_POS_SERVER_URL='http://127.0.0.1:1',
                   BROOST_SYNC_KEY='isolated-test-only')
        with (target / 'startup.txt').open('w', encoding='utf-8') as log:
            process = subprocess.Popen([str(target / 'BroostPOS.exe')], cwd=target, env=env,
                                       stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                for _ in range(120):
                    if process.poll() is not None:
                        raise RuntimeError(f'POS exited during startup: {process.returncode}')
                    if (target / 'broost_pos.db').exists():
                        conn = sqlite3.connect(target / 'broost_pos.db')
                        try:
                            settings = dict(conn.execute('SELECT key,value FROM settings'))
                            if settings.get('app_password') and settings.get('web_server_url') == 'http://127.0.0.1:1':
                                time.sleep(3)
                                if process.poll() is not None:
                                    raise RuntimeError('POS exited after database initialization')
                                break
                        except sqlite3.OperationalError:
                            pass
                        finally:
                            conn.close()
                    time.sleep(.25)
                else:
                    raise RuntimeError('POS startup timed out')
            finally:
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=10)
        errors = (target / 'startup.txt').read_text(encoding='utf-8', errors='replace')
        if 'Traceback' in errors:
            raise RuntimeError(errors[-2000:])
        defaults = json.loads((source / '_internal/pos_defaults.json').read_text(encoding='utf-8'))
        print('PASS: packaged POS startup, isolated database, initial login settings')
        print('Bundled server URL:', defaults.get('server_url'))


if __name__ == '__main__':
    main()
