"""Verify the compiled cloud shell with a localhost-only page and printer bridge."""
import argparse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--app-dir',type=Path,required=True);args=parser.parse_args()
    ready=threading.Event()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers()
            self.wfile.write(b'''<html><body>Cloud smoke test<script>setInterval(()=>{if(window.broostPrinter&&window.BROOST_POS_DEVICE_KEY==='isolated-test-only'&&window.BROOST_POS_TERMINAL_ID)fetch('/ready',{method:'POST'});},100);</script></body></html>''')
        def do_POST(self):
            if self.path=='/ready':ready.set()
            self.send_response(200);self.end_headers()
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with tempfile.TemporaryDirectory(prefix='broost-cloud-smoke-') as folder:
            target=Path(folder)
            shutil.copytree(args.app_dir/'_internal',target/'_internal')
            shutil.copy2(args.app_dir/'BroostPOS.exe',target/'BroostPOS.exe')
            env=os.environ.copy();env.update(QT_QPA_PLATFORM='offscreen',QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu',
                BROOST_POS_SERVER_URL=f'http://127.0.0.1:{server.server_port}',BROOST_SYNC_KEY='isolated-test-only')
            with (target/'startup.log').open('w') as log:
                process=subprocess.Popen([str(target/'BroostPOS.exe')],cwd=target,env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
                try:
                    if not ready.wait(40):raise RuntimeError('Cloud shell failed to load the trusted page and native printer bridge')
                    if process.poll() is not None:raise RuntimeError('Cloud shell exited unexpectedly')
                    if list(target.glob('*.db')):raise RuntimeError('Cloud shell created a local operational database')
                finally:
                    subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
                    process.wait(timeout=10)
            if 'Traceback' in (target/'startup.log').read_text(errors='replace'):
                raise RuntimeError('Cloud shell reported a Python startup failure')
            print('PASS: packaged cloud UI, isolated credentials, native printer bridge, no local operational database.')
    finally:
        server.shutdown();server.server_close()


if __name__=='__main__':main()
