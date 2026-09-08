"""Bounded, read-only installation checks. Never persist credentials or sales."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import ssl
import sys
import tempfile
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler

VERSION = '2.1'  # Setup schema; a visual hotfix must not invalidate completed setup.
APP_VERSION = '2.1.1'


def connection_fingerprint(defaults):
    return hashlib.sha256((defaults['server_url']+'\n'+defaults['sync_key']).encode()).hexdigest()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # Do not forward the device credential to another origin.


def request_json(base, path, headers=None, body=None):
    import certifi
    parsed = urlsplit(base)
    if (parsed.scheme != 'https' and not
            (parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1'))):
        raise ValueError('invalid server')
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('invalid server')
    opener = build_opener(NoRedirect(), HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())))
    request = Request(base.rstrip('/')+path, headers={'Content-Type':'application/json', **(headers or {})},
                      data=json.dumps(body).encode() if body is not None else None)
    with opener.open(request, timeout=10) as response:
        data = json.loads(response.read(2_000_001))
        if not isinstance(data, dict):
            raise ValueError('invalid response')
        return data


def error_message(exc):
    if isinstance(exc, HTTPError):
        return {401:'رمز الكاشير أو ربط الجهاز غير صحيح. راجع الرمز أو استخدم أحدث نسخة من المثبّت.',
                403:'السيرفر رفض صلاحية هذا الجهاز.',
                404:'السيرفر يحتاج تحديثًا يدعم فحص التجهيز.',
                429:'محاولات دخول كثيرة. انتظر خمس دقائق ثم أعد المحاولة.'}.get(
                    exc.code, 'السيرفر لم يكمل الطلب. أعد المحاولة، وإن استمرت المشكلة أرسل تقرير الفحص.')
    reason = getattr(exc, 'reason', exc)
    if isinstance(reason, ssl.SSLError):
        return 'تعذر التحقق من شهادة الاتصال. راجع تاريخ ووقت Windows ثم أعد المحاولة.'
    if isinstance(reason, socket.gaierror):
        return 'تعذر الوصول إلى عنوان السيرفر. راجع الإنترنت وإعدادات DNS.'
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return 'انتهت مهلة الاتصال. راجع الإنترنت وأعد الاختبار.'
    if isinstance(exc, (URLError, OSError)):
        return 'تعذر الاتصال بالسيرفر. تأكد من الإنترنت والسماح للبرنامج بالاتصال.'
    return 'استجابة السيرفر غير متوافقة. راجع إصدار البرنامج والسيرفر.'


def check_connection(defaults, pin, progress=lambda text: None):
    try:
        progress('جارٍ اختبار السيرفر وقاعدة البيانات…')
        health = request_json(defaults['server_url'], '/health')
        if health.get('status') != 'ok':
            raise ValueError('health')
        progress('جارٍ التحقق من صلاحية دخول الكاشير…')
        login = request_json(defaults['server_url'], '/api/pos/login',
                             {'X-Sync-Key':defaults['sync_key']}, {'pin':pin})
        token = login.get('token')
        if not isinstance(token, str) or not token:
            raise ValueError('login')
        progress('جارٍ قراءة المنيو والتحقق من التشغيل السحابي…')
        result = request_json(defaults['server_url'], '/api/pos/diagnostics', {'X-Pos-Token':token})
        if result.get('status') != 'ok' or result.get('cloud_only') is not True:
            return {'ok':False,'message':'السيرفر غير مجهز لوضع Cloud فقط. يلزم مراجعة إعداد الربط.'}
        count = int(result['menu_items'])
        if count <= 0:
            return {'ok':False,'message':'الربط ناجح لكن المنيو فارغ. أضف الأصناف من لوحة الإدارة ثم أعد الاختبار.'}
        remote = datetime.fromisoformat(result['time'].replace('Z','+00:00'))
        if remote.tzinfo is None:
            remote = remote.replace(tzinfo=timezone.utc)
        skew = abs((datetime.now(timezone.utc)-remote).total_seconds())
        if skew > 300:
            return {'ok':False,'message':'وقت الجهاز يختلف عن السيرفر بأكثر من خمس دقائق. فعّل ضبط الوقت تلقائيًا في Windows ثم أعد الاختبار.'}
        return {'ok':True,'message':f'نجح الاتصال والدخول وقراءة {count} صنفًا. التشغيل سحابي فقط.',
                'menu_items':count,'checked_at':datetime.now(timezone.utc).isoformat()}
    except Exception as exc:
        return {'ok':False,'message':error_message(exc)}


def device_checks(directory):
    rows = []
    supported = sys.platform == 'win32' and sys.maxsize > 2**32
    if supported:
        supported = sys.getwindowsversion().build >= 19045
    rows.append({'name':'نظام التشغيل','ok':supported,
                 'message':'Windows 10 إصدار 22H2 أو Windows 11 بنظام 64 بت مطلوب.' if not supported else 'إصدار Windows وبنية الجهاز متوافقان.'})
    try:
        Path(directory).mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=directory) as probe:
            probe.write(b'broost-settings-check'); probe.flush()
        rows.append({'name':'حفظ إعدادات الجهاز','ok':True,'message':'صلاحيات الكتابة سليمة.'})
        free = shutil.disk_usage(directory).free
        rows.append({'name':'المساحة المتاحة','ok':free >= 256*1024**2,
                     'message':f'المتاح {free//(1024**2)} ميجابايت؛ يلزم 256 ميجابايت على الأقل للتشغيل.'})
    except OSError:
        rows.append({'name':'حفظ إعدادات الجهاز','ok':False,'message':'تعذر حفظ الإعدادات. راجع صلاحيات مجلد المستخدم والمساحة.'})
    return rows


def set_autostart(enabled, executable=None):
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
        if enabled:
            if not getattr(sys, 'frozen', False) and executable is None:
                raise OSError('Autostart requires installed application')
            winreg.SetValueEx(key, 'BroostCloudPOS', 0, winreg.REG_SZ,
                             '"'+str(executable or sys.executable)+'"')
        else:
            try:
                winreg.DeleteValue(key, 'BroostCloudPOS')
            except FileNotFoundError:
                pass


def autostart_enabled():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run') as key:
            return bool(winreg.QueryValueEx(key, 'BroostCloudPOS')[0])
    except (OSError, ImportError):
        return False


def safe_report(checks, connection, printer_confirmed, paper_width):
    # Allowlist only. Never serialize settings, HTTP bodies, PIN, token or key.
    return {'app_version':APP_VERSION,'created_at':datetime.now(timezone.utc).isoformat(),
            'windows':platform.version(),
            'checks':[{'name':str(r['name']),'ok':bool(r['ok']),'message':str(r['message'])} for r in checks],
            'connection_ok':bool(connection.get('ok')),'connection_result':connection.get('message','لم يُختبر'),
            'physical_print_confirmed':bool(printer_confirmed),'paper_width_mm':paper_width}
