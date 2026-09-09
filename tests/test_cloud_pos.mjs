import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import {randomUUID} from 'node:crypto';
const source=readFileSync(new URL('../webapp/static/pos.js',import.meta.url),'utf8');
function harness(handler){
  const elements=new Map();
  function get(id){if(!elements.has(id))elements.set(id,{value:'',hidden:true,open:false,innerHTML:'',textContent:'',querySelectorAll(){return[];},showModal(){this.open=true;},close(){this.open=false;},reset(){},classList:{toggle(){}}});return elements.get(id);}
  get('#fulfillment').value='PICKUP';get('#payment').value='CASH';
  const context=vm.createContext({console,crypto:{randomUUID},AbortSignal,URL,encodeURIComponent,setInterval(){},
    sessionStorage:{getItem(){return'';},setItem(){}},window:{addEventListener(){},BROOST_POS_TERMINAL_ID:'terminal-test'},
    document:{querySelector:get,querySelectorAll(){return[];},addEventListener(){}},
    fetch:async(url,options)=>{const result=await handler(url,options);return{ok:!result?.error,status:result?.error||200,json:async()=>result?.error?{detail:'Invalid amount'}:result};}});
  vm.runInContext(source,context);
  const run=code=>vm.runInContext(code,context);
  run("state.token='test';state.data={shift:{id:1},menu:{version:1},areas:[],orders:[],drivers:[]};state.cart=[{name:'Meal',quantity:3,unit_price:135,item_id:'meal',offer_id:null,size_id:null,extra_ids:[],spicy:false}]");
  return{run,get};
}
const order={id:1,public_number:'POS-00001',source:'POS',status:'COMPLETED',payment_method:'CASH',subtotal:405,total:405,items:[]};
const data={shift:{id:1},menu:{version:1,categories:[],items:[],offers:[]},areas:[],orders:[],drivers:[]};
test('an uncertain save retains its request and cart; retry acknowledges one invoice',async()=>{
  const requests=[];let failed=false;
  const h=harness(async(url,options)=>{
    if(url==='/api/pos/orders'){requests.push(JSON.parse(options.body));if(!failed){failed=true;throw Error('connection lost');}return order;}
    return url==='/api/pos/state'?data:{};
  });
  await h.run("$('#checkout').onsubmit({preventDefault(){}})");
  assert.equal(h.run('state.cart.length'),1);assert(h.run('state.pending'));
  await h.run("$('#checkout').onsubmit({preventDefault(){}})");
  assert.equal(requests.length,2);assert.equal(requests[0].request_id,requests[1].request_id);
  assert.equal(h.run('state.pending'),null);assert.equal(h.run('state.cart.length'),0);assert.equal(h.run('state.receipt.id'),1);
});
test('a rejected invoice can be corrected without discarding the cart',async()=>{
  const h=harness(async url=>url==='/api/pos/orders'?{error:422}:{});
  await h.run("$('#checkout').onsubmit({preventDefault(){}})");
  assert.equal(h.run('state.pending'),null);assert.equal(h.run('state.cart.length'),1);
  assert.equal(h.get('#notice').textContent,'Invalid amount');
});
test('cashier and kitchen receipts escape customer notes and include item details',()=>{
  const h=harness(async()=>({}));
  const html=h.run(`receiptHtml({id:3,items:[{item_name:'Meal',size_name:'Large',quantity:2,unit_price:50,extras:[{name:'Sauce'}]}],notes:'<script>bad</script>',total:100},true)`);
  assert(html.includes('Meal'));assert(html.includes('Sauce'));assert(html.includes('&lt;script&gt;'));
  assert(!html.includes('<script>bad'));
});

test('renderActive updates activeBadge count and renders active orders',async()=>{
  const h=harness(async()=>({}));
  h.run(`
    state.data.orders=[
      {id:10,status:'PREPARING',fulfillment:'PICKUP',items:[],total:100},
      {id:11,status:'DISPATCHED',fulfillment:'DELIVERY',items:[],total:150},
      {id:12,status:'COMPLETED',fulfillment:'PICKUP',items:[],total:200},
      {id:13,status:'CANCELLED',fulfillment:'PICKUP',items:[],total:50}
    ];
    renderActive();
  `);
  assert.equal(h.get('#activeBadge').textContent,'2');
  assert(h.get('#activeOrders').innerHTML.includes('#10'));
  assert(h.get('#activeOrders').innerHTML.includes('#11'));
  assert(!h.get('#activeOrders').innerHTML.includes('#12'));
});

test('editOrder populates cart and sends edit_order_id upon submission',async()=>{
  const requests=[];
  const h=harness(async(url,options)=>{
    if(url==='/api/pos/orders'){requests.push(JSON.parse(options.body));return{id:5,status:'COMPLETED',items:[]};}
    return{};
  });
  h.run(`
    state.data.menu={
      version:1,
      items:[{sync_id:'m1',name:'برجر لحم',base_price:90}],
      sizes:[{sync_id:'s1',item_sync_id:'m1',name:'دبل',price_offset:30}],
      extras:[{sync_id:'e1',item_sync_id:'m1',name:'جبنة',price:15}],
      offers:[]
    };
    state.cart=[];
    const orderToEdit={
      id:5,
      pos_revision:2,
      fulfillment:'PICKUP',
      payment_method:'CASH',
      customer_name:'محمد',
      customer_phone:'01012345678',
      discount:10,
      cash_received:120,
      notes:'بدون بصل',
      items:[{
        menu_item_sync_id:'m1',
        item_name:'برجر لحم',
        size_name:'دبل',
        quantity:1,
        unit_price:135,
        extras:[{name:'جبنة'}]
      }]
    };
    editOrder(orderToEdit);
  `);
  assert.equal(h.run('state.editing.id'),5);
  assert.equal(h.run('state.cart.length'),1);
  assert.equal(h.run('state.cart[0].unit_price'),135);
  assert.equal(h.get('#cartTitle').textContent,'تعديل الفاتورة #5');

  await h.run("$('#checkout').onsubmit({preventDefault(){}})");
  assert.equal(requests.length,1);
  assert.equal(requests[0].edit_order_id,5);
  assert.equal(requests[0].expected_revision,2);
  assert.equal(h.run('state.editing'),null);
  assert.equal(h.run('state.cart.length'),0);
});

test('incoming online order triggers onlineOrderAlert and updates alert fields',async()=>{
  const h=harness(async()=>({}));
  h.run(`
    state.data.orders=[
      {id:42,source:'ONLINE',status:'NEW',fulfillment:'DELIVERY',customer_name:'سامح',total:280}
    ];
    checkIncomingOnlineOrders();
  `);
  assert.equal(h.get('#onlineOrderAlert').hidden, false);
  assert.equal(h.get('#alertOrderNumber').textContent, '#42');
  assert.equal(h.get('#alertCustomerName').textContent, 'سامح');
  assert.equal(h.get('#alertOrderFulfillment').textContent, 'دليفري');
});

