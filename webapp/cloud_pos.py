"""Cloud cashier commands. All sales share the website's canonical orders table."""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timezone, timedelta
from typing import Literal

from fastapi import Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ConfigDict


def backend():
    from webapp import server
    return server


def init_cloud_schema(conn):
    s = backend()
    identity = 'BIGSERIAL PRIMARY KEY' if s.USING_POSTGRES else 'INTEGER PRIMARY KEY AUTOINCREMENT'
    conn.execute(f'''CREATE TABLE IF NOT EXISTS pos_shifts (
        id {identity}, cashier_name TEXT NOT NULL, opened_at TEXT NOT NULL,
        closed_at TEXT, opening_cash REAL NOT NULL DEFAULT 0, actual_cash REAL)''')
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_open_pos_shift ON pos_shifts ((1)) WHERE closed_at IS NULL")
    conn.execute(f'''CREATE TABLE IF NOT EXISTS pos_drivers (
        id {identity}, name TEXT NOT NULL UNIQUE, phone TEXT NOT NULL DEFAULT '', is_active INTEGER NOT NULL DEFAULT 1)''')
    conn.execute(f'''CREATE TABLE IF NOT EXISTS pos_cash_movements (
        id {identity}, request_id TEXT UNIQUE NOT NULL, shift_id INTEGER NOT NULL REFERENCES pos_shifts(id),
        amount REAL NOT NULL, reason TEXT NOT NULL, driver_id INTEGER REFERENCES pos_drivers(id), created_at TEXT NOT NULL)''')
    columns = s.table_columns(conn, 'orders')
    for name, kind in (('pos_shift_id','INTEGER REFERENCES pos_shifts(id)'), ('cash_received','REAL'), ('change_due','REAL'), ('pos_revision','INTEGER NOT NULL DEFAULT 0')):
        if name not in columns:
            conn.execute(f'ALTER TABLE orders ADD COLUMN {name} {kind}')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_orders_pos_shift ON orders(pos_shift_id)')
    conn.execute('CREATE TABLE IF NOT EXISTS pos_drafts (terminal_id TEXT PRIMARY KEY, request_id TEXT NOT NULL, payload_json TEXT NOT NULL)')
    conn.execute('CREATE TABLE IF NOT EXISTS pos_edit_requests (request_id TEXT PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE)')


def active_shift(conn):
    return conn.execute('SELECT * FROM pos_shifts WHERE closed_at IS NULL ORDER BY id DESC LIMIT 1').fetchone()


def lock_sales(conn):
    if backend().USING_POSTGRES:
        conn.execute('SELECT pg_advisory_xact_lock(2026090801)')


def session_secret(conn):
    s = backend()
    return s.setting(conn, 'active_sync_key', '') or s.setting(conn, 'sync_key')


def require_session(x_pos_token: str = Header(default='')):
    s = backend()
    try:
        expiry, nonce, signature = x_pos_token.split('.')
        with s.db_connection() as conn:
            secret = session_secret(conn)
        expected = hmac.new(secret.encode(), f'{expiry}.{nonce}'.encode(), hashlib.sha256).hexdigest()
        if int(expiry) <= time.time() or not hmac.compare_digest(signature, expected):
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail='انتهت جلسة الكاشير؛ سجّل الدخول من جديد')


class MoneyInput(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)


class LoginInput(BaseModel):
    pin: str = Field(min_length=1, max_length=120)


class ShiftInput(MoneyInput):
    opening_cash: float = Field(default=0, ge=0, le=10000000)


class CloseShiftInput(MoneyInput):
    actual_cash: float = Field(ge=0, le=10000000)


class MovementInput(MoneyInput):
    request_id: str = Field(min_length=8, max_length=120)
    amount: float = Field(ge=-10000000, le=10000000)
    reason: str = Field(min_length=2, max_length=300)
    driver_id: int | None = None


class DriverInput(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    phone: str = Field(default='', max_length=30)


class LineInput(BaseModel):
    item_id: str | None = None
    offer_id: str | None = None
    quantity: int = Field(ge=1, le=30)
    size_id: str | None = None
    extra_ids: list[str] = Field(default_factory=list, max_length=30)
    spicy: bool = False


class SaleInput(MoneyInput):
    request_id: str = Field(min_length=8, max_length=120)
    fulfillment: Literal['PICKUP','DELIVERY'] = 'PICKUP'
    payment_method: Literal['CASH','WALLET','VISA'] = 'CASH'
    customer_name: str = Field(default='عميل المطعم', max_length=120)
    customer_phone: str = Field(default='', max_length=30)
    area_id: int | None = None
    detailed_address: str = Field(default='', max_length=500)
    notes: str = Field(default='', max_length=500)
    discount: float = Field(default=0, ge=0, le=10000000)
    cash_received: float = Field(default=0, ge=0, le=10000000)
    items: list[LineInput] = Field(min_length=1, max_length=80)
    edit_order_id: int | None = None
    expected_revision: int | None = None


class StatusInput(BaseModel):
    status: Literal['PREPARING','READY','DISPATCHED','COMPLETED','CANCELLED']
    driver_id: int | None = None
    payment_status: Literal['CONFIRMED','REJECTED'] | None = None


def terminal_id(x_pos_terminal: str = Header(min_length=8,max_length=120)):
    return x_pos_terminal


def shift_summary(conn, shift):
    row = conn.execute('''SELECT 
        COALESCE(SUM(CASE WHEN status!='CANCELLED' THEN total ELSE 0 END),0) AS sales,
        COALESCE(SUM(CASE WHEN status!='CANCELLED' THEN total-delivery_fee ELSE 0 END),0) AS net_sales,
        COALESCE(SUM(CASE WHEN status!='CANCELLED' AND payment_method='CASH' THEN total ELSE 0 END),0) AS cash,
        COALESCE(SUM(CASE WHEN status!='CANCELLED' AND payment_method='WALLET' THEN total ELSE 0 END),0) AS wallet,
        COALESCE(SUM(CASE WHEN status!='CANCELLED' AND payment_method='VISA' THEN total ELSE 0 END),0) AS visa,
        COALESCE(SUM(CASE WHEN status!='CANCELLED' THEN delivery_fee ELSE 0 END),0) AS delivery_fees,
        COUNT(CASE WHEN status!='CANCELLED' THEN 1 END) AS invoices 
        FROM orders WHERE pos_shift_id=?''',(shift['id'],)).fetchone()
    movements = conn.execute('SELECT COALESCE(SUM(amount),0) AS total FROM pos_cash_movements WHERE shift_id=?',(shift['id'],)).fetchone()['total']
    return {
        **dict(shift), 
        **dict(row), 
        'movements_total': round(float(movements), 2),
        'expected_cash': round(float(shift['opening_cash'])+float(row['cash'])+float(movements),2)
    }


def driver_balances(conn):
    result=[]
    for driver in conn.execute('SELECT * FROM pos_drivers ORDER BY name').fetchall():
        charged=conn.execute('''SELECT COALESCE(SUM(CASE WHEN payment_method='CASH' THEN total-delivery_fee ELSE -delivery_fee END),0) AS total
            FROM orders WHERE driver_name=? AND status IN ('DISPATCHED','COMPLETED') AND fulfillment='DELIVERY' ''',(driver['name'],)).fetchone()['total']
        paid=conn.execute('SELECT COALESCE(SUM(amount),0) AS total FROM pos_cash_movements WHERE driver_id=?',(driver['id'],)).fetchone()['total']
        result.append({**dict(driver),'balance':round(float(charged)-float(paid),2)})
    return result


def create_sale(payload: SaleInput):
    s=backend()
    with s.db_connection(immediate=True) as conn:
        lock_sales(conn)
        request_id='CLOUD:'+payload.request_id
        existing=conn.execute('SELECT * FROM orders WHERE client_request_id=?',(request_id,)).fetchone()
        if payload.edit_order_id:
            existing=conn.execute('SELECT o.* FROM orders o JOIN pos_edit_requests e ON e.order_id=o.id WHERE e.request_id=?',(request_id,)).fetchone()
        if existing:
            return s.order_to_dict(conn,existing)
        shift=active_shift(conn)
        if not shift:
            raise HTTPException(409,'افتح الوردية قبل تسجيل الفاتورة')
        original=None
        if payload.edit_order_id:
            original=s.select_for_update(conn,'SELECT * FROM orders WHERE id=?',(payload.edit_order_id,))
            if not original or original['status'] == 'CANCELLED':
                raise HTTPException(404,'الطلب غير موجود أو ملغي ولا يمكن تعديله')
            if original['pos_shift_id'] and original['pos_shift_id'] != shift['id']:
                raise HTTPException(409,'التعديل متاح لطلبات الوردية الحالية فقط')
            if payload.expected_revision!=original['pos_revision']:
                raise HTTPException(409,'الفاتورة اتغيرت؛ افتح أحدث نسخة قبل التعديل')
            if payload.fulfillment!=original['fulfillment']:
                raise HTTPException(409,'نوع الفاتورة المحفوظة لا يتغير؛ ألغها وأنشئ طلبًا جديدًا عند الحاجة')
        phone=s.normalize_phone(payload.customer_phone)
        if phone and not s.valid_egyptian_mobile(phone):
            raise HTTPException(422,'رقم الموبايل غير صحيح')
        fee=0.0; area_name=''
        address=payload.detailed_address.strip()
        if payload.fulfillment=='DELIVERY':
            area=conn.execute('SELECT * FROM delivery_areas WHERE id=? AND is_active=1 AND delivery_enabled=1',(payload.area_id,)).fetchone()
            if not area or not phone or not address or len(payload.customer_name.strip())<2:
                raise HTTPException(422,'الدليفري يحتاج اسم العميل ورقمه والمنطقة والعنوان')
            fee=float(area['delivery_fee']); area_name=area['name']
        items,subtotal=s.calculate_order_items(conn,payload.items)
        if payload.discount>subtotal:
            raise HTTPException(422,'الخصم يتجاوز قيمة الأصناف')
        total=round(subtotal+fee-payload.discount,2)
        cash=payload.cash_received or total
        if payload.payment_method=='CASH' and payload.fulfillment=='PICKUP' and cash<total:
            raise HTTPException(422,'المبلغ المدفوع أقل من الفاتورة')
        now=s.utc_now()
        created=datetime.now(s.ZoneInfo('Africa/Cairo')).strftime('%Y-%m-%d %H:%M:%S')
        values={'resume_token':secrets.token_urlsafe(24),'client_request_id':request_id,'source':'POS',
                'fulfillment':payload.fulfillment,'customer_name':payload.customer_name.strip() or 'عميل المطعم',
                'customer_phone':phone,'customer_phone_normalized':phone,'area_id':payload.area_id if fee or area_name else None,
                'area_name':area_name,'detailed_address':s.strip_area_prefix(address,area_name),
                'payment_method':payload.payment_method,'payment_status':'CONFIRMED' if payload.fulfillment=='PICKUP' or payload.payment_method!='CASH' else 'CASH_ON_DELIVERY',
                'status':'COMPLETED' if payload.fulfillment=='PICKUP' else 'PREPARING','subtotal':subtotal,'delivery_fee':fee,
                'discount':payload.discount,'total':total,'notes':payload.notes,'cashier_name':shift['cashier_name'],
                'created_at':created,'updated_at':now,'closed_at':now if payload.fulfillment=='PICKUP' else None,
                'pos_shift_id':shift['id'],'cash_received':cash if payload.payment_method=='CASH' and payload.fulfillment=='PICKUP' else None,
                'change_due':round(cash-total,2) if payload.payment_method=='CASH' and payload.fulfillment=='PICKUP' else 0}
        if original:
            for field in ('resume_token','client_request_id','source','created_at','pos_shift_id'):
                values.pop(field,None)
            values['pos_revision']=original['pos_revision']+1
            values['status']=original['status']
            values['closed_at']=original['closed_at']
            values['payment_status']=original['payment_status']
            if not original['pos_shift_id']:
                values['pos_shift_id']=shift['id']
            order_id=original['id']
            conn.execute(f"UPDATE orders SET {','.join(key+'=?' for key in values)} WHERE id=?",(*values.values(),order_id))
            conn.execute('DELETE FROM order_items WHERE order_id=?',(order_id,))
            conn.execute('INSERT INTO pos_edit_requests(request_id,order_id) VALUES (?,?)',(request_id,order_id))
        else:
            cursor=conn.execute(f"INSERT INTO orders ({','.join(values)}) VALUES ({','.join('?' for _ in values)})",tuple(values.values()))
            order_id=cursor.lastrowid
            conn.execute('UPDATE orders SET public_number=?,local_order_id=? WHERE id=?',(f'POS-{order_id:05d}',order_id,order_id))
        conn.executemany('''INSERT INTO order_items(order_id,menu_item_sync_id,item_name,size_name,quantity,unit_price,extras_json)
            VALUES (?,?,?,?,?,?,?)''',[(order_id,i['menu_item_sync_id'],i['item_name'],i['size_name'],i['quantity'],i['unit_price'],json.dumps(i['extras'],ensure_ascii=False)) for i in items])
        s.emit_event(conn,order_id,'ORDER_UPDATED' if original else 'ORDER_CREATED',{'source':'POS'})
        return s.order_to_dict(conn,conn.execute('SELECT * FROM orders WHERE id=?',(order_id,)).fetchone())


def install_cloud_routes(app):
    s=backend()
    s._RATE_RULES[('POST','/api/pos/login')]=(8,300)

    @app.get('/pos',include_in_schema=False)
    def page():
        return FileResponse(s.STATIC_DIR/'pos.html',headers={'Cache-Control':'no-store'})

    @app.post('/api/pos/login')
    def login(payload:LoginInput,request:Request,x_sync_key:str=Header(default='')):
        if x_sync_key:
            s.require_sync(x_sync_key)
            with s.db_connection() as conn:
                pin=s.setting(conn,'cloud_cashier_pin','1111')
            if not secrets.compare_digest(pin.encode(),payload.pin.encode()):
                raise HTTPException(401,'رمز الكاشير غير صحيح')
        else:
            s.verify_admin_secret(request,payload.pin)
        with s.db_connection() as conn:
            secret=session_secret(conn)
        message=f'{int(time.time())+16*3600}.{secrets.token_hex(16)}'
        return {'token':message+'.'+hmac.new(secret.encode(),message.encode(),hashlib.sha256).hexdigest()}

    @app.get('/api/pos/diagnostics',dependencies=[Depends(require_session)])
    def diagnostics():
        # Installation must not expire orders, open shifts, or consume invoice IDs.
        with s.db_connection() as conn:
            menu=s.read_menu(conn)
            return {'status':'ok','time':s.utc_now(),'release':s.APP_RELEASE,
                    'cloud_only':s.setting(conn,'cloud_pos_only','0')=='1',
                    'menu_items':len(menu['items']),'categories':len(menu['categories'])}

    @app.get('/api/pos/state',dependencies=[Depends(require_session)])
    def state():
        with s.db_connection() as conn:
            shift=active_shift(conn)
            s.set_setting(conn,'pos_last_seen_at',s.utc_now())
            s.set_setting(conn,'pos_shift_open','1' if shift else '0')
            s.set_setting(conn,'pos_shift_opened_at',shift['opened_at'] if shift else '')
            s.expire_unaccepted_orders(conn)
            return {'menu':s.read_menu(conn),'areas':[dict(r) for r in conn.execute('SELECT * FROM delivery_areas ORDER BY sort_order,name')],
                    'shift':shift_summary(conn,shift) if shift else None,'drivers':driver_balances(conn),
                    'orders':s.admin_orders_to_dict(conn,conn.execute("SELECT * FROM orders WHERE status NOT IN ('COMPLETED','CANCELLED') ORDER BY id DESC").fetchall())}

    @app.get('/api/pos/history',dependencies=[Depends(require_session)])
    def history(offset:int=0, q:str='', fulfillment:str=''):
        if offset<0: raise HTTPException(422,'صفحة غير صحيحة')
        with s.db_connection() as conn:
            clauses = []
            params = []
            q_clean = q.strip()
            if q_clean:
                if q_clean.isdigit():
                    clauses.append("(id=? OR public_number LIKE ? OR customer_phone LIKE ?)")
                    params.extend([int(q_clean), f"%{q_clean}%", f"%{q_clean}%"])
                else:
                    clauses.append("(public_number LIKE ? OR customer_name LIKE ? OR customer_phone LIKE ?)")
                    params.extend([f"%{q_clean}%", f"%{q_clean}%", f"%{q_clean}%"])
            if fulfillment in ('PICKUP', 'DELIVERY'):
                clauses.append("fulfillment=?")
                params.append(fulfillment)
            where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
            sql = f"SELECT * FROM orders {where_sql} ORDER BY id DESC LIMIT 100 OFFSET ?"
            params.append(offset)
            return s.admin_orders_to_dict(conn, conn.execute(sql, tuple(params)).fetchall())

    @app.get('/api/pos/day-summary',dependencies=[Depends(require_session)])
    def day_summary(start:str=''):
        with s.db_connection() as conn:
            start_iso = ''
            if start.strip():
                parsed = s.parse_utc_datetime(start.strip())
                if parsed:
                    start_iso = parsed.isoformat().replace("+00:00", "Z")
            if not start_iso:
                shift = active_shift(conn)
                if shift and shift['opened_at']:
                    start_iso = shift['opened_at']
                else:
                    now_utc = datetime.now(timezone.utc)
                    cutoff = now_utc.replace(hour=5, minute=0, second=0, microsecond=0)
                    if now_utc < cutoff:
                        cutoff -= timedelta(days=1)
                    start_iso = cutoff.isoformat().replace("+00:00", "Z")

            shift = active_shift(conn)
            shift_id = shift['id'] if shift else -1
            date_prefix = start_iso[:10]

            orders_rows = conn.execute(
                "SELECT * FROM orders WHERE (pos_shift_id = ? OR substr(created_at, 1, 10) >= ?) ORDER BY id ASC",
                (shift_id, date_prefix)
            ).fetchall()
            orders = s.admin_orders_to_dict(conn, orders_rows)

            shift_info = shift_summary(conn, shift) if shift else None

            total_orders = len(orders)
            completed_orders = [o for o in orders if o['status'] == 'COMPLETED']
            cancelled_orders = [o for o in orders if o['status'] == 'CANCELLED']
            active_orders = [o for o in orders if o['status'] not in ('COMPLETED', 'CANCELLED')]

            revenue_orders = [o for o in orders if (o['source'] == 'POS' and o['status'] != 'CANCELLED') or (o['source'] != 'POS' and o['status'] == 'COMPLETED')]

            total_sales = sum(float(o.get('total') or 0) for o in revenue_orders)
            net_sales = sum(float(o.get('subtotal') or 0) - float(o.get('discount') or 0) for o in revenue_orders)
            delivery_fees = sum(float(o.get('delivery_fee') or 0) for o in revenue_orders)
            discounts = sum(float(o.get('discount') or 0) for o in revenue_orders)

            pickup_orders = [o for o in revenue_orders if o['fulfillment'] == 'PICKUP']
            delivery_orders = [o for o in revenue_orders if o['fulfillment'] == 'DELIVERY']

            pickup_total = sum(float(o.get('total') or 0) for o in pickup_orders)
            delivery_total = sum(float(o.get('total') or 0) for o in delivery_orders)

            cash_orders = [o for o in revenue_orders if o.get('payment_method') == 'CASH']
            wallet_orders = [o for o in revenue_orders if o.get('payment_method') == 'WALLET']
            visa_orders = [o for o in revenue_orders if o.get('payment_method') == 'VISA']

            cash_total = sum(float(o.get('total') or 0) for o in cash_orders)
            wallet_total = sum(float(o.get('total') or 0) for o in wallet_orders)
            visa_total = sum(float(o.get('total') or 0) for o in visa_orders)

            pos_orders = [o for o in revenue_orders if o['source'] == 'POS']
            online_orders = [o for o in revenue_orders if o['source'] != 'POS']

            top_items_rows = conn.execute("""
                SELECT oi.item_name, SUM(oi.quantity) AS qty, SUM(oi.quantity * oi.unit_price) AS sales
                FROM order_items oi
                JOIN orders o ON oi.order_id = o.id
                WHERE (o.pos_shift_id = ? OR substr(o.created_at, 1, 10) >= ?) AND o.status != 'CANCELLED'
                GROUP BY oi.item_name
                ORDER BY qty DESC
                LIMIT 10
            """, (shift_id, date_prefix)).fetchall()

            top_items = [{'name': r['item_name'], 'quantity': r['qty'], 'sales': round(float(r['sales']), 2)} for r in top_items_rows]

            return {
                'start_time': start_iso,
                'generated_at': s.utc_now(),
                'cashier_name': shift_info.get('cashier_name') if shift_info else s.setting(conn, 'cloud_cashier_name', 'DR OMAR'),
                'shift_id': shift_info.get('id') if shift_info else None,
                'total_orders': total_orders,
                'completed_orders_count': len(completed_orders),
                'active_orders_count': len(active_orders),
                'cancelled_orders_count': len(cancelled_orders),
                'total_sales': round(total_sales, 2),
                'net_sales': round(net_sales, 2),
                'delivery_fees': round(delivery_fees, 2),
                'discounts': round(discounts, 2),
                'pickup_count': len(pickup_orders),
                'pickup_total': round(pickup_total, 2),
                'delivery_count': len(delivery_orders),
                'delivery_total': round(delivery_total, 2),
                'pos_count': len(pos_orders),
                'pos_total': round(sum(float(o.get('total') or 0) for o in pos_orders), 2),
                'online_count': len(online_orders),
                'online_total': round(sum(float(o.get('total') or 0) for o in online_orders), 2),
                'cash_total': round(cash_total, 2),
                'wallet_total': round(wallet_total, 2),
                'visa_total': round(visa_total, 2),
                'expected_cash': shift_info.get('expected_cash') if shift_info else round(cash_total, 2),
                'top_items': top_items
            }

    @app.get('/api/pos/customers',dependencies=[Depends(require_session)])
    def customers(phone:str=''):
        with s.db_connection() as conn:
            rows=conn.execute("SELECT * FROM orders WHERE customer_phone_normalized=? ORDER BY id DESC LIMIT 20",(s.normalize_phone(phone),)).fetchall()
            return s.admin_orders_to_dict(conn,rows)

    @app.post('/api/pos/orders',dependencies=[Depends(require_session)])
    def sale(payload:SaleInput): return create_sale(payload)

    @app.get('/api/pos/draft',dependencies=[Depends(require_session)])
    def get_draft(terminal:str=Depends(terminal_id)):
        with s.db_connection() as conn:
            row=conn.execute('SELECT payload_json FROM pos_drafts WHERE terminal_id=?',(terminal,)).fetchone()
            return json.loads(row['payload_json']) if row else None

    @app.put('/api/pos/draft',dependencies=[Depends(require_session)])
    def put_draft(payload:SaleInput,terminal:str=Depends(terminal_id)):
        with s.db_connection(immediate=True) as conn:
            lock_sales(conn)
            existing=conn.execute('SELECT request_id FROM pos_drafts WHERE terminal_id=?',(terminal,)).fetchone()
            if existing and existing['request_id']!=payload.request_id:
                raise HTTPException(409,'يوجد طلب سابق لم يتم تأكيد نتيجته؛ أعد الاتصال لاستعادته')
            conn.execute('INSERT INTO pos_drafts(terminal_id,request_id,payload_json) VALUES (?,?,?) ON CONFLICT(terminal_id) DO UPDATE SET payload_json=excluded.payload_json',
                (terminal,payload.request_id,payload.model_dump_json()))
            return {'ok':True}

    @app.delete('/api/pos/draft',dependencies=[Depends(require_session)])
    def clear_draft(request_id:str,terminal:str=Depends(terminal_id)):
        with s.db_connection() as conn:
            conn.execute('DELETE FROM pos_drafts WHERE terminal_id=? AND request_id=?',(terminal,request_id))
            return {'ok':True}

    @app.patch('/api/pos/orders/{order_id}',dependencies=[Depends(require_session)])
    def status(order_id:int,payload:StatusInput):
        changes={'status':payload.status,'payment_status':payload.payment_status}
        with s.db_connection() as conn:
            if payload.driver_id:
                driver=conn.execute('SELECT * FROM pos_drivers WHERE id=? AND is_active=1',(payload.driver_id,)).fetchone()
                if not driver: raise HTTPException(404,'الطيار غير موجود')
                changes['driver_name']=driver['name']
        return s.update_admin_order(order_id,s.OrderAdminUpdate(**changes))

    @app.post('/api/pos/shifts',dependencies=[Depends(require_session)])
    def open_shift(payload:ShiftInput):
        with s.db_connection(immediate=True) as conn:
            lock_sales(conn)
            shift=active_shift(conn)
            if not shift:
                cursor=conn.execute('INSERT INTO pos_shifts(cashier_name,opened_at,opening_cash) VALUES (?,?,?)',
                    (s.setting(conn,'cloud_cashier_name','DR OMAR'),s.utc_now(),payload.opening_cash))
                shift=conn.execute('SELECT * FROM pos_shifts WHERE id=?',(cursor.lastrowid,)).fetchone()
            return shift_summary(conn,shift)

    @app.post('/api/pos/shifts/{shift_id}/close',dependencies=[Depends(require_session)])
    def close_shift(shift_id:int,payload:CloseShiftInput):
        with s.db_connection(immediate=True) as conn:
            lock_sales(conn)
            shift=s.select_for_update(conn,'SELECT * FROM pos_shifts WHERE id=?',(shift_id,))
            if not shift: raise HTTPException(404,'الوردية غير موجودة')
            if shift['closed_at']: return shift_summary(conn,shift)
            if conn.execute("SELECT id FROM orders WHERE pos_shift_id=? AND status NOT IN ('COMPLETED','CANCELLED') LIMIT 1",(shift_id,)).fetchone():
                raise HTTPException(409,'أكمل أو ألغِ الطلبات الجارية قبل إغلاق الوردية')
            conn.execute('UPDATE pos_shifts SET closed_at=?,actual_cash=? WHERE id=?',(s.utc_now(),payload.actual_cash,shift_id))
            s.set_setting(conn,'pos_shift_open','0')
            return shift_summary(conn,conn.execute('SELECT * FROM pos_shifts WHERE id=?',(shift_id,)).fetchone())

    @app.get('/api/pos/shifts',dependencies=[Depends(require_session)])
    def shifts():
        with s.db_connection() as conn:
            return [shift_summary(conn,r) for r in conn.execute('SELECT * FROM pos_shifts ORDER BY id DESC LIMIT 100').fetchall()]

    @app.post('/api/pos/movements',dependencies=[Depends(require_session)])
    def movement(payload:MovementInput):
        with s.db_connection(immediate=True) as conn:
            lock_sales(conn)
            existing=conn.execute('SELECT id FROM pos_cash_movements WHERE request_id=?',(payload.request_id,)).fetchone()
            if existing: return {'id':existing['id']}
            shift=active_shift(conn)
            if not shift: raise HTTPException(409,'افتح الوردية أولًا')
            if payload.driver_id and not conn.execute('SELECT id FROM pos_drivers WHERE id=?',(payload.driver_id,)).fetchone():
                raise HTTPException(404,'الطيار غير موجود')
            cursor=conn.execute('INSERT INTO pos_cash_movements(request_id,shift_id,amount,reason,driver_id,created_at) VALUES (?,?,?,?,?,?)',
                (payload.request_id,shift['id'],payload.amount,payload.reason,payload.driver_id,s.utc_now()))
            return {'id':cursor.lastrowid}

    @app.post('/api/pos/drivers',dependencies=[Depends(require_session)])
    def driver(payload:DriverInput):
        with s.db_connection(immediate=True) as conn:
            lock_sales(conn)
            conn.execute('INSERT INTO pos_drivers(name,phone) VALUES (?,?) ON CONFLICT(name) DO UPDATE SET phone=excluded.phone',
                (payload.name.strip(),payload.phone.strip()))
            return driver_balances(conn)

    @app.get('/api/pos/orders/{order_id}/proof',dependencies=[Depends(require_session)])
    def proof(order_id:int): return s.get_admin_proof(order_id)
