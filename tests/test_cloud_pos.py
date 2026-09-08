import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from webapp import server as s


class CloudPOSTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        root=Path(self.temp.name)
        self.patches=[patch.object(s,'DATA_DIR',root),patch.object(s,'DB_PATH',root/'web.db'),
            patch.object(s,'PROOFS_DIR',root/'proofs'),patch.object(s,'USING_POSTGRES',False)]
        for p in self.patches:p.start()
        s.init_web_db()
        s._RATE_BUCKETS.clear()
        with s.db_connection() as conn:
            for k,v in [('active_sync_key','cloud-test-key'),('cloud_cashier_pin','1234'),('admin_password','test-admin')]:s.set_setting(conn,k,v)
            conn.execute("INSERT INTO categories(sync_id,local_id,name,sort_order,updated_at) VALUES ('cat',1,'Food',1,'2026-01-01')")
            conn.execute("INSERT INTO menu_items(sync_id,local_id,category_sync_id,name,base_price,updated_at) VALUES ('meal',1,'cat','Meal',100,'2026-01-01')")
            conn.execute("INSERT INTO delivery_areas(name,delivery_fee,updated_at) VALUES ('Area',15,'2026-01-01')")
        self.client=TestClient(s.app)
        r=self.client.post('/api/pos/login',headers={'X-Sync-Key':'cloud-test-key'},json={'pin':'1234'})
        self.assertEqual(r.status_code,200,r.text)
        self.headers={'X-Pos-Token':r.json()['token'],'X-Pos-Terminal':'test-terminal'}
        self.payload={'request_id':'sale-request-1','items':[{'item_id':'meal','quantity':2}],'discount':10,'cash_received':200}

    def tearDown(self):
        self.client.close()
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()

    def post(self,path,body):return self.client.post('/api/pos/'+path,headers=self.headers,json=body)
    def open(self):
        r=self.post('shifts',{'opening_cash':50});self.assertEqual(r.status_code,200,r.text);return r.json()

    def test_sale_is_canonical_and_retry_cannot_duplicate(self):
        self.open()
        def save(_):return self.post('orders',self.payload)
        with ThreadPoolExecutor(max_workers=4) as pool: responses=list(pool.map(save,range(4)))
        for r in responses:self.assertEqual(r.status_code,200,r.text)
        self.assertEqual({r.json()['id'] for r in responses},{1})
        order=responses[0].json();self.assertEqual(order['total'],190);self.assertEqual(order['change_due'],10)
        admin=self.client.get('/api/admin/orders',headers={'X-Admin-Key':'test-admin'}).json()
        self.assertEqual(len(admin),1);self.assertEqual(admin[0]['id'],order['id']);self.assertEqual(admin[0]['items'][0]['quantity'],2)
        state=self.client.get('/api/pos/state',headers=self.headers).json()
        self.assertEqual(state['shift']['expected_cash'],240)

    def test_admin_cancellation_updates_cloud_cash_immediately_once(self):
        self.open();order=self.post('orders',self.payload).json()
        for _ in range(2):
            r=self.client.patch('/api/admin/orders/'+str(order['id']),headers={'X-Admin-Key':'test-admin'},json={'status':'CANCELLED'})
            self.assertEqual(r.status_code,200,r.text)
        state=self.client.get('/api/pos/state',headers=self.headers).json()
        self.assertEqual(state['shift']['expected_cash'],50)

    def test_bad_values_and_closed_shift_do_not_write_sales(self):
        self.assertEqual(self.post('orders',self.payload).status_code,409)
        self.open()
        for changes in ({'discount':300},{'cash_received':5},{'items':[{'item_id':'missing','quantity':1}]},{'fulfillment':'DELIVERY'}):
            self.assertIn(self.post('orders',{**self.payload,**changes}).status_code,(409,422))
        self.assertEqual(self.client.get('/api/pos/history',headers=self.headers).json(),[])

    def test_draft_survives_session_restart_and_only_matching_ack_clears_it(self):
        self.open()
        self.assertEqual(self.client.put('/api/pos/draft',headers=self.headers,json=self.payload).status_code,200)
        original=self.post('orders',self.payload).json()
        recovered=self.client.get('/api/pos/draft',headers=self.headers).json()
        self.assertEqual(self.post('orders',recovered).json()['id'],original['id'])
        self.client.delete('/api/pos/draft?request_id=wrong',headers=self.headers)
        self.assertIsNotNone(self.client.get('/api/pos/draft',headers=self.headers).json())
        self.client.delete('/api/pos/draft?request_id=sale-request-1',headers=self.headers)
        self.assertIsNone(self.client.get('/api/pos/draft',headers=self.headers).json())

    def test_delivery_settlement_and_shift_close_are_idempotent(self):
        shift=self.open()
        driver=self.post('drivers',{'name':'Driver','phone':'01000000000'}).json()[0]
        order=self.post('orders',{**self.payload,'fulfillment':'DELIVERY','customer_name':'Customer','customer_phone':'01000000000','area_id':1,'detailed_address':'Street'}).json()
        for status in ('DISPATCHED','COMPLETED'):
            r=self.client.patch('/api/pos/orders/'+str(order['id']),headers=self.headers,json={'status':status,'driver_id':driver['id']})
            self.assertEqual(r.status_code,200,r.text)
        state=self.client.get('/api/pos/state',headers=self.headers).json()
        self.assertEqual(state['drivers'][0]['balance'],190)
        self.assertEqual(self.post(f"shifts/{shift['id']}/close",{'actual_cash':50}).status_code,409)
        payload={'request_id':'settlement-1','amount':190,'reason':'Delivery settlement','driver_id':driver['id']}
        for _ in range(2):self.assertEqual(self.post('movements',payload).status_code,200)
        state=self.client.get('/api/pos/state',headers=self.headers).json()
        self.assertEqual(state['drivers'][0]['balance'],0);self.assertEqual(state['shift']['expected_cash'],240)
        for _ in range(2):self.assertEqual(self.post(f"shifts/{shift['id']}/close",{'actual_cash':240}).status_code,200)

    def test_unauthorized_sessions_and_legacy_uploads_are_blocked(self):
        self.assertEqual(self.client.get('/api/pos/state').status_code,401)
        self.assertEqual(self.client.get('/api/pos/state',headers={'X-Pos-Token':self.headers['X-Pos-Token']+'bad'}).status_code,401)
        with s.db_connection() as conn:s.set_setting(conn,'cloud_pos_only','1')
        r=self.client.post('/api/sync/pos-orders',headers={'X-Sync-Key':'cloud-test-key'},json={'orders':[{'local_order_id':99,'total':500}]})
        self.assertEqual(r.status_code,410)
        self.assertEqual(self.client.get('/api/pos/history',headers=self.headers).json(),[])

    def test_edit_keeps_invoice_identity_and_retries_do_not_add_sales(self):
        self.open();order=self.post('orders',self.payload).json()
        payload={**self.payload,'request_id':'edit-request-1','edit_order_id':order['id'],'expected_revision':0,'discount':20}
        for _ in range(2):
            response=self.post('orders',payload);self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.json()['id'],order['id']);self.assertEqual(response.json()['total'],180)
        state=self.client.get('/api/pos/state',headers=self.headers).json()
        self.assertEqual(state['shift']['expected_cash'],230)
        self.assertEqual(state['shift']['invoices'],1)
        stale=self.post('orders',{**payload,'request_id':'edit-request-2','discount':30})
        self.assertEqual(stale.status_code,409)


if __name__=='__main__':unittest.main()
