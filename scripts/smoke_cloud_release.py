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
from datetime import datetime,timezone


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--app-dir',type=Path,required=True)
    parser.add_argument('--screenshots-dir',type=Path);args=parser.parse_args()
    ready=threading.Event()
    login_calls=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            if self.path in ('/health','/api/pos/diagnostics'):
                self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
                self.wfile.write(json.dumps({'status':'ok','time':datetime.now(timezone.utc).isoformat(),
                    'cloud_only':True,'menu_items':42,'categories':8}).encode());return
            self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers()
            self.wfile.write(b'''<html><body>Cloud smoke test<script>setInterval(()=>{if(window.broostPrinter&&window.BROOST_POS_DEVICE_KEY==='isolated-test-only'&&window.BROOST_POS_TERMINAL_ID)fetch('/ready',{method:'POST'});},100);</script></body></html>''')
        def do_POST(self):
            if self.path=='/api/pos/login':
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if body!={'pin':'isolated-test-pin'} or self.headers.get('X-Sync-Key')!='isolated-test-only':
                    self.send_response(401);self.end_headers();return
                login_calls.append(True)
                self.send_response(200);self.end_headers();self.wfile.write(b'{"token":"isolated-token"}');return
            if self.path=='/ready':ready.set()
            self.send_response(200);self.end_headers()
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with tempfile.TemporaryDirectory(prefix='broost-cloud-smoke-') as folder:
            target=Path(folder)
            fonts=target/'qa-fonts';fonts.mkdir()
            for name in ('tahoma.ttf','tahomabd.ttf'):
                font=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/name
                if font.is_file():shutil.copy2(font,fonts/name)
            shutil.copytree(args.app_dir/'_internal',target/'_internal')
            shutil.copy2(args.app_dir/'BroostPOS.exe',target/'BroostPOS.exe')
            env=os.environ.copy();env.update(QT_QPA_PLATFORM='offscreen',QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu',
                BROOST_POS_SERVER_URL=f'http://127.0.0.1:{server.server_port}',BROOST_SYNC_KEY='isolated-test-only',
                BROOST_SMOKE_SETTINGS=str(target/'smoke-settings.ini'))
            env['QT_QPA_FONTDIR']=str(fonts)
            with (target/'startup.log').open('w') as log:
                process=subprocess.Popen([str(target/'BroostPOS.exe'),'--setup-smoke'],cwd=target,env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
                try:
                    if not ready.wait(40):raise RuntimeError('Cloud shell failed to load the trusted page and native printer bridge')
                    if process.poll() is not None:raise RuntimeError('Cloud shell exited unexpectedly')
                    if list(target.glob('*.db')):raise RuntimeError('Cloud shell created a local operational database')
                    saved=(target/'smoke-settings.ini').read_text()
                    if 'setup_version=2.1' not in saved or 'isolated-test-pin' in saved or 'isolated-test-only' in saved:
                        raise RuntimeError('Setup settings were not persisted safely')
                finally:
                    subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
                    process.wait(timeout=10)
            if 'Traceback' in (target/'startup.log').read_text(errors='replace'):
                raise RuntimeError('Cloud shell reported a Python startup failure')
            ready.clear()
            with (target/'restart.log').open('w') as log:
                process=subprocess.Popen([str(target/'BroostPOS.exe'),'--setup-smoke'],cwd=target,env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
                try:
                    if not ready.wait(25) or len(login_calls)!=1:
                        raise RuntimeError('Restart did not retain completed setup')
                finally:
                    subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
                    process.wait(timeout=10)
            if args.screenshots_dir:
                args.screenshots_dir.mkdir(parents=True,exist_ok=True)
                for screenshot in target.glob('setup-*.png'):shutil.copy2(screenshot,args.screenshots_dir/screenshot.name)
            print('PASS: setup wizard, read-only connection, simulated print confirmation, retained settings on restart, cloud UI and printer bridge; no local sales database or persisted credentials.')
    finally:
        server.shutdown();server.server_close()


if __name__=='__main__':main()
