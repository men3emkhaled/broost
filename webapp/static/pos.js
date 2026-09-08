/* Cloud-only cashier: no IndexedDB, localStorage, SQLite or offline upload queue. */
const $=q=>document.querySelector(q), esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const money=n=>`${Number(n||0).toLocaleString('ar-EG',{maximumFractionDigits:2})} ج`;
const statusNames={NEW:'جديد',PREPARING:'جاري التجهيز',READY:'جاهز',DISPATCHED:'خرج مع الطيار',COMPLETED:'مكتمل',CANCELLED:'ملغي'};
const state={token:'',data:null,cart:[],receipt:null,offset:0,pending:null,refreshing:false,busy:false,editing:null};
const terminal=window.BROOST_POS_TERMINAL_ID||sessionStorage.getItem('broost_terminal')||crypto.randomUUID();
if(!window.BROOST_POS_TERMINAL_ID)sessionStorage.setItem('broost_terminal',terminal);
const base=String(window.BROOST_CONFIG?.apiBaseUrl||'').replace(/\/$/,'');
function notice(text){$('#notice').textContent=text;$('#notice').hidden=!text;}
function connection(ok){$('#connection').textContent=ok?'● متصل بالسيرفر':'● الاتصال متوقف — الحفظ غير مؤكد';$('#connection').className=ok?'online':'offline';}
async function api(path,method='GET',body){
  let response;
  try{response=await fetch(base+path,{method,headers:{'Content-Type':'application/json','X-Pos-Token':state.token,'X-Pos-Terminal':terminal},body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(20000),cache:'no-store'});}
  catch(error){connection(false);throw new Error('تعذر تأكيد العملية. تأكد من الاتصال ثم أعد المحاولة؛ لا تُنشئ فاتورة بديلة.');}
  const data=await response.json().catch(()=>({}));
  if(response.status===401){if(!$('#login').open)$('#login').showModal();}
  if(!response.ok){const error=new Error(typeof data.detail==='string'?data.detail:'راجع البيانات المدخلة');error.status=response.status;throw error;}
  connection(true);return data;
}
async function run(fn){try{await fn();}catch(e){notice(e.message);}}
async function refresh(){
  if(!state.token||state.refreshing)return;
  state.refreshing=true;
  try{const previousVersion=state.data?.menu.version;state.data=await api('/api/pos/state');if(previousVersion!==state.data.menu.version)renderMenu();renderAccounts();renderActive();totals();if(!$('#orders').hidden)await loadHistory();}
  catch(e){connection(false);notice(e.message);}finally{state.refreshing=false;}
}
function renderMenu(){
  const m=state.data.menu,selected=$('#category').value,area=$('#area').value;
  $('#category').innerHTML='<option value="">كل الأقسام</option>'+m.categories.map(c=>`<option value="${esc(c.sync_id)}">${esc(c.name)}</option>`).join('')+'<option value="offers">العروض</option>';
  $('#category').value=selected;
  $('#area').innerHTML='<option value="">اختر المنطقة</option>'+state.data.areas.filter(a=>a.is_active&&a.delivery_enabled).map(a=>`<option value="${a.id}">${esc(a.name)} — ${money(a.delivery_fee)}</option>`).join('');
  $('#area').value=area;
  const query=$('#search').value.trim();
  let items=m.items.filter(i=>i.is_available&&(!selected||i.category_sync_id===selected)).map(i=>({...i,kind:'item'}));
  if(!selected||selected==='offers')items.push(...m.offers.filter(o=>o.is_active).map(o=>({...o,base_price:o.offer_price,kind:'offer'})));
  $('#products').innerHTML=items.filter(i=>i.name.includes(query)).map(i=>`<button class="product" data-product="${esc(i.sync_id)}" data-kind="${i.kind}"><b>${esc(i.name)}</b><span>${money(i.base_price)}</span></button>`).join('')||'<p>لا توجد أصناف بهذه الخيارات.</p>';
}
let selectedItem=null;
function chooseItem(id,kind){
  if(state.pending){notice('يوجد طلب جارٍ تأكيده؛ أعد محاولة حفظه أولًا.');return;}
  const m=state.data.menu,item=(kind==='offer'?m.offers:m.items).find(i=>i.sync_id===id);
  selectedItem={item,kind};$('#itemName').textContent=item.name;
  $('#size').innerHTML='<option value="">عادي</option>'+(kind==='offer'?'':m.sizes.filter(s=>s.item_sync_id===id).map(s=>`<option value="${esc(s.sync_id)}">${esc(s.name)} (+${money(s.price_offset)})</option>`).join(''));
  $('#extras').innerHTML=kind==='offer'?'':m.extras.filter(e=>e.item_sync_id===id).map(e=>`<label><input type="checkbox" value="${esc(e.sync_id)}">${esc(e.name)} (+${money(e.price)})</label>`).join('');
  $('#spicy').checked=false;$('#spicy').disabled=kind==='offer';$('#quantity').value=1;$('#itemDialog').showModal();
}
$('#itemForm').onsubmit=e=>{e.preventDefault();const {item,kind}=selectedItem,m=state.data.menu;
  const size=m.sizes.find(s=>s.sync_id===$('#size').value),extras=[...$('#extras').querySelectorAll('input:checked')].map(i=>m.extras.find(x=>x.sync_id===i.value));
  state.cart.push({name:item.name,size:size?.name||'عادي',unit_price:Number(kind==='offer'?item.offer_price:item.base_price)+Number(size?.price_offset||0)+extras.reduce((s,x)=>s+Number(x.price),0),
    item_id:kind==='item'?item.sync_id:null,offer_id:kind==='offer'?item.sync_id:null,size_id:size?.sync_id||null,extra_ids:extras.map(x=>x.sync_id),spicy:$('#spicy').checked,quantity:Number($('#quantity').value)});
  $('#itemDialog').close();renderCart();};
function renderCart(){
  $('#cartTitle').textContent=state.editing?'تعديل الفاتورة #'+state.editing.id:'الفاتورة الجديدة';
  $('#cartLines').innerHTML=state.cart.map((i,n)=>`<div class="line"><div><b>${esc(i.name)}</b><small>${esc(i.size)} · ${i.quantity} × ${money(i.unit_price)}${i.spicy?' · حار':''}</small></div><strong>${money(i.quantity*i.unit_price)}</strong><button data-remove="${n}" ${state.pending?'disabled':''}>×</button></div>`).join('')||'<p>اختر الأصناف لإضافة طلب.</p>';
  totals();
}
function totals(){
  const sub=state.cart.reduce((s,i)=>s+i.quantity*i.unit_price,0),delivery=$('#fulfillment').value==='DELIVERY';
  const fee=delivery?Number(state.data?.areas.find(a=>a.id===Number($('#area').value))?.delivery_fee||0):0;
  const total=sub+fee-Number($('#discount').value||0);
  $('#areaLabel').hidden=!delivery;$('#addressLabel').hidden=!delivery;
  $('#totals').innerHTML=`${money(total)}<small>الأصناف ${money(sub)} · التوصيل ${money(fee)}</small>`;
  $('#submitSale').disabled=state.busy||(!state.cart.length&&!state.pending)||(!state.data?.shift&&!state.pending);
  $('#checkout').querySelectorAll('input,select').forEach(e=>e.disabled=!!state.pending);
  $('#lookup').disabled=!!state.pending;
  $('#submitSale').textContent=state.pending?'إعادة تأكيد نفس الفاتورة':state.data?.shift?(state.editing?'حفظ تعديل الفاتورة #'+state.editing.id:'حفظ الفاتورة'):'افتح الوردية أولًا';
}
$('#checkout').onsubmit=e=>{e.preventDefault();return run(async()=>{
  if(state.busy)return;
  if(!state.pending)state.pending={request_id:crypto.randomUUID(),edit_order_id:state.editing?.id||null,expected_revision:state.editing?.pos_revision??null,fulfillment:$('#fulfillment').value,payment_method:$('#payment').value,
    customer_name:$('#customerName').value||'عميل المطعم',customer_phone:$('#phone').value,area_id:Number($('#area').value)||null,detailed_address:$('#address').value,
    discount:Number($('#discount').value||0),cash_received:Number($('#cash').value||0),notes:$('#notes').value,
    items:state.cart.map(({item_id,offer_id,quantity,size_id,extra_ids,spicy})=>({item_id,offer_id,quantity,size_id,extra_ids,spicy}))};
  state.busy=true;totals();
  try{await api('/api/pos/draft','PUT',state.pending);const order=await api('/api/pos/orders','POST',state.pending);await api('/api/pos/draft?request_id='+encodeURIComponent(state.pending.request_id),'DELETE');state.pending=null;state.editing=null;state.cart=[];$('#checkout').reset();renderCart();notice(`تم حفظ الفاتورة #${order.id} على السيرفر`);showReceipt(order);await refresh();}
  catch(error){if(error.status>=400&&error.status<500&&error.status!==401){await api('/api/pos/draft?request_id='+encodeURIComponent(state.pending.request_id),'DELETE');state.pending=null;}throw error;}
  finally{state.busy=false;totals();}
});};
function receiptHtml(order,kitchen=false){
  const lines=order.items.map(i=>`<tr><td>${esc(i.item_name)}<br><small>${esc(i.size_name)} ${esc((i.extras||[]).map(e=>e.name).join('، '))}</small></td><td>${i.quantity}</td>${kitchen?'':`<td>${money(i.quantity*i.unit_price)}</td>`}</tr>`).join('');
  return `<html dir="rtl"><head><meta charset="utf-8"><style>body{font-family:Tahoma;text-align:center;font-size:12px}table{width:100%;border-collapse:collapse}td{padding:6px;border-bottom:1px solid #ddd}small{font-size:10px}h2{font-size:20px}</style></head><body><h2>بروست</h2><h3>${kitchen?'نسخة المطبخ':'فاتورة العميل'} #${order.id}</h3><p>${esc(order.public_number)}<br>${esc(order.created_at)}</p><p>${esc(order.customer_name)}<br>${esc(order.customer_phone)}<br>${esc(order.area_name)} ${esc(order.detailed_address)}</p><table>${lines}</table>${kitchen?'':`<p>الأصناف ${money(order.subtotal)}<br>الخصم ${money(order.discount)}<br>التوصيل ${money(order.delivery_fee)}</p><h2>الإجمالي ${money(order.total)}</h2><p>${esc({CASH:'نقدي',WALLET:'محفظة',VISA:'فيزا'}[order.payment_method])} · ${esc(statusNames[order.status])}</p><p>الباقي ${money(order.change_due)}</p>`}<p>${esc(order.notes)}</p><p>الكاشير: ${esc(order.cashier_name)}<br>الطيار: ${esc(order.driver_name)}</p><p>0552802874 · 01092453841</p></body></html>`;
}
function showReceipt(order){state.receipt=order;$('#receipt').innerHTML=receiptHtml(order).match(/<body>([\s\S]*)<\/body>/)[1];if(!$('#receiptDialog').open)$('#receiptDialog').showModal();}
async function printReceipt(kitchen){
  if(!state.receipt)return;
  const html=receiptHtml(state.receipt,kitchen);
  if(window.broostPrinter){window.broostPrinter.printHtml(html);return;}
  $('#receipt').innerHTML=html.match(/<body>([\s\S]*)<\/body>/)[1];window.print();
}
function orderCard(o){return `<article class="order-card"><div class="toolbar"><b>#${o.id} · ${money(o.total)}</b><span class="badge">${esc(statusNames[o.status])}</span><span>${o.source==='POS'?'المطعم':'أونلاين'}</span></div><p>${esc(o.customer_name)} · ${esc(o.customer_phone)}<br>${esc(o.area_name)} ${esc(o.detailed_address)}<br>${esc(o.notes)}</p><p>${o.items.map(i=>`${i.quantity} × ${esc(i.item_name)}`).join(' · ')}</p><div class="toolbar"><button data-receipt="${o.id}">تفاصيل / طباعة</button>${o.source==='POS'&&o.pos_shift_id===state.data?.shift?.id&&['PREPARING','COMPLETED'].includes(o.status)?`<button data-edit="${o.id}">تعديل</button>`:''}${o.has_payment_proof?`<button data-proof="${o.id}">إثبات التحويل</button>`:''}${o.status==='NEW'?`<button data-status="PREPARING" data-id="${o.id}">قبول وتجهيز</button>`:''}${o.status==='PREPARING'&&o.fulfillment==='PICKUP'?`<button data-status="READY" data-id="${o.id}">جاهز</button>`:''}${['PREPARING','READY'].includes(o.status)&&o.fulfillment==='DELIVERY'?`<button data-status="DISPATCHED" data-id="${o.id}">تعيين طيار وخروج</button>`:''}${(o.status==='DISPATCHED'||o.fulfillment==='PICKUP'&&['PREPARING','READY'].includes(o.status))?`<button data-status="COMPLETED" data-id="${o.id}">تم التسليم</button>`:''}${o.status!=='CANCELLED'?`<button data-status="CANCELLED" data-id="${o.id}">إلغاء</button>`:''}</div></article>`;}
function renderActive(){$('#activeOrders').innerHTML=state.data.orders.map(orderCard).join('')||'<p>لا توجد طلبات جارية.</p>';}
let history=[];
async function loadHistory(){history=await api('/api/pos/history?offset='+state.offset);$('#history').innerHTML=history.map(orderCard).join('')||'<p>لا توجد فواتير محفوظة.</p>';$('#previous').disabled=state.offset===0;$('#next').disabled=history.length<100;}
function findOrder(id){return [...(state.data?.orders||[]),...history].find(o=>o.id===Number(id));}
function ask(title,fields){return new Promise(resolve=>{
  $('#inputTitle').textContent=title;$('#inputFields').innerHTML=fields.map(f=>`<label>${esc(f.label)}${f.options?`<select name="${f.name}">${f.options.map(o=>`<option value="${esc(o.value)}">${esc(o.label)}</option>`).join('')}</select>`:`<input name="${f.name}" type="${f.type||'text'}" value="${esc(f.value||'')}" ${f.type==='number'?'step="0.01"':''} required>`}</label>`).join('');
  const d=$('#inputDialog');let done=false;d.onclose=()=>{if(!done)resolve(null);};$('#inputForm').onsubmit=e=>{e.preventDefault();done=true;const data=Object.fromEntries(new FormData(e.target));d.close();resolve(data);};d.showModal();
});}
async function changeStatus(id,status){const order=findOrder(id);let driver_id=null,payment_status=null;
  if(status==='CANCELLED'){if(!await ask('تأكيد إلغاء الفاتورة #'+id,[{name:'confirm',label:'تأكيد',options:[{value:'yes',label:'إلغاء الفاتورة'}]}]))return;}
  if(status==='DISPATCHED'){const answer=await ask('اختر الطيار',[{name:'driver',label:'الطيار',options:state.data.drivers.filter(d=>d.is_active).map(d=>({value:d.id,label:d.name}))}]);if(!answer)return;driver_id=Number(answer.driver);if(!driver_id)throw new Error('أضف طيارًا أولًا');}
  if(order.payment_method==='WALLET'&&order.payment_status==='PROOF_UPLOADED'&&status==='PREPARING'){
    if(!await ask('تأكيد استلام التحويل',[{name:'confirm',label:'بعد مراجعة الإثبات',options:[{value:'yes',label:'تم استلام المبلغ'}]}]))return;payment_status='CONFIRMED';
  }
  await api('/api/pos/orders/'+id,'PATCH',{status,driver_id,payment_status});notice('تم تحديث الفاتورة');await refresh();await loadHistory();
}
function editOrder(order){
  if(state.cart.length||state.pending){notice('أكمل الفاتورة الحالية أولًا.');return;}
  const m=state.data.menu;
  const cart=order.items.map(line=>{
    const item=m.items.find(i=>i.sync_id===line.menu_item_sync_id);
    const offer=!item&&m.offers.find(o=>'عرض: '+o.name===line.item_name);
    if(!item&&!offer)throw new Error('الصنف لم يعد موجودًا في المنيو؛ راجع الإدارة قبل تعديل الفاتورة.');
    const size=item&&m.sizes.find(s=>s.item_sync_id===item.sync_id&&s.name===line.size_name);
    const extras=item?m.extras.filter(e=>e.item_sync_id===item.sync_id&&(line.extras||[]).some(x=>x.name===e.name)):[];
    return {name:item?.name||offer.name,size:size?.name||'عادي',unit_price:Number(item?.base_price??offer.offer_price)+Number(size?.price_offset||0)+extras.reduce((a,e)=>a+Number(e.price),0),item_id:item?.sync_id||null,offer_id:offer?.sync_id||null,size_id:size?.sync_id||null,extra_ids:extras.map(e=>e.sync_id),spicy:(line.extras||[]).some(e=>e.system_key==='spicy'),quantity:line.quantity};
  });
  state.editing=order;state.cart=cart;
  for(const [id,value] of Object.entries({fulfillment:order.fulfillment,payment:order.payment_method,customerName:order.customer_name,phone:order.customer_phone,area:order.area_id||'',address:order.detailed_address||'',discount:order.discount,cash:order.cash_received||0,notes:order.notes||''}))$('#'+id).value=value;
  document.querySelectorAll('.tab').forEach(t=>t.hidden=t.id!=='sale');
  document.querySelectorAll('nav [data-tab]').forEach(t=>t.classList.toggle('active',t.dataset.tab==='sale'));
  renderCart();notice('تعديل الفاتورة #'+order.id+' — الأسعار تُراجع من المنيو الحالي عند الحفظ.');
}
function renderAccounts(){const shift=state.data.shift;$('#shift').innerHTML=shift?`<p>وردية #${shift.id} — ${esc(shift.cashier_name)}</p><h2>النقد المتوقع ${money(shift.expected_cash)}</h2><p>مبيعات الأصناف ${money(shift.sales)} · ${shift.invoices} فاتورة</p>`:'<p>لا توجد وردية مفتوحة.</p>';
  $('#openShift').disabled=!!shift;$('#closeShift').disabled=!shift;$('#movement').disabled=!shift;
  $('#drivers').innerHTML=state.data.drivers.map(d=>`<div class="line"><div><b>${esc(d.name)}</b><small>${esc(d.phone)}</small></div><b>${money(d.balance)}</b><button data-settle="${d.id}">تسوية</button></div>`).join('');}
async function loadShifts(){const rows=await api('/api/pos/shifts');$('#shifts').innerHTML=`<table><tr><th>الوردية</th><th>المبيعات</th><th>المتوقع</th><th>الفعلي</th><th>فرق الجرد</th></tr>${rows.map(s=>`<tr><td>#${s.id}<small>${esc(s.opened_at)} ${s.closed_at?'مغلقة':'مفتوحة'}</small></td><td>${money(s.sales)}</td><td>${money(s.expected_cash)}</td><td>${s.actual_cash===null?'—':money(s.actual_cash)}</td><td>${s.actual_cash===null?'—':money(s.actual_cash-s.expected_cash)}</td></tr>`).join('')}</table>`;}
$('#openShift').onclick=()=>run(async()=>{const a=await ask('فتح الوردية',[{name:'cash',label:'عهدة بداية الوردية',type:'number',value:'0'}]);if(a){await api('/api/pos/shifts','POST',{opening_cash:Number(a.cash)});await refresh();await loadShifts();notice('الوردية مفتوحة؛ يمكنك تسجيل الطلبات.');}});
$('#closeShift').onclick=()=>run(async()=>{const a=await ask('إغلاق الوردية',[{name:'cash',label:'النقد الفعلي في الدرج',type:'number',value:state.data.shift.expected_cash}]);if(a){await api('/api/pos/shifts/'+state.data.shift.id+'/close','POST',{actual_cash:Number(a.cash)});await refresh();await loadShifts();}});
// Keep monetary command IDs across retries until their outcome is confirmed.
let pendingMovement=null;
async function sendMovement(data){if(!pendingMovement)pendingMovement={request_id:crypto.randomUUID(),...data};await api('/api/pos/movements','POST',pendingMovement);pendingMovement=null;await refresh();await loadShifts();}
$('#movement').onclick=()=>run(async()=>{if(pendingMovement){await sendMovement();return;}const a=await ask('مصروف أو إيداع',[{name:'amount',label:'المبلغ: سالب للمصروف، موجب للإيداع',type:'number'},{name:'reason',label:'البيان'}]);if(a)await sendMovement({amount:Number(a.amount),reason:a.reason});});
$('#addDriver').onclick=()=>run(async()=>{const a=await ask('إضافة طيار',[{name:'name',label:'الاسم'},{name:'phone',label:'الموبايل'}]);if(a){await api('/api/pos/drivers','POST',a);await refresh();}});
$('#lookup').onclick=()=>run(async()=>{const orders=await api('/api/pos/customers?phone='+encodeURIComponent($('#phone').value));if(!orders.length){notice('لا يوجد سجل سابق لهذا الرقم.');return;}const o=orders[0];$('#customerName').value=o.customer_name;$('#address').value=o.detailed_address||'';$('#area').value=o.area_id||'';notice(`تم تحميل بيانات العميل — آخر فاتورة #${o.id}`);totals();});
$('#loginForm').onsubmit=e=>{e.preventDefault();run(async()=>{try{const response=await fetch(base+'/api/pos/login',{method:'POST',headers:{'Content-Type':'application/json','X-Sync-Key':window.BROOST_POS_DEVICE_KEY||''},body:JSON.stringify({pin:$('#pin').value}),signal:AbortSignal.timeout(20000)});const data=await response.json();if(!response.ok)throw new Error(data.detail||'تعذر الدخول');state.token=data.token;$('#pin').value='';$('#login').close();await refresh();state.pending=await api('/api/pos/draft');totals();notice(state.pending?'يوجد طلب لم تُؤكّد نتيجته قبل الإغلاق. اضغط إعادة تأكيد نفس الفاتورة لاستعادته.':'افتح الوردية من «الوردية والطيارون» لبدء البيع.');}catch(e){$('#loginError').textContent=e.message;}});};
$('#logout').onclick=()=>{if(state.pending||state.cart.length){notice('أكمل الفاتورة الحالية قبل الخروج.');return;}state.token='';$('#login').showModal();};
$('#admin').onclick=()=>window.open('https://broost-three.vercel.app/admin','_blank');
$('#search').oninput=()=>state.data&&renderMenu();$('#category').onchange=()=>renderMenu();
for(const selector of ['#fulfillment','#area','#discount','#cash','#payment'])$(selector).oninput=totals;
$('#refreshOrders').onclick=()=>run(async()=>{await refresh();await loadHistory();});
$('#previous').onclick=()=>run(async()=>{state.offset=Math.max(0,state.offset-100);await loadHistory();});
$('#next').onclick=()=>run(async()=>{state.offset+=100;await loadHistory();});
$('#printReceipt').onclick=()=>printReceipt(false);$('#printKitchen').onclick=()=>printReceipt(true);
document.addEventListener('click',e=>run(async()=>{const b=e.target.closest('button');if(!b)return;
  if(b.dataset.close)$('#'+b.dataset.close).close();
  if(b.dataset.product)chooseItem(b.dataset.product,b.dataset.kind);
  if(b.dataset.remove!==undefined&&!state.pending){state.cart.splice(Number(b.dataset.remove),1);renderCart();}
  if(b.dataset.tab){document.querySelectorAll('.tab').forEach(t=>t.hidden=t.id!==b.dataset.tab);document.querySelectorAll('nav [data-tab]').forEach(t=>t.classList.toggle('active',t===b));if(b.dataset.tab==='orders')await loadHistory();if(b.dataset.tab==='accounts')await loadShifts();}
  if(b.dataset.edit)editOrder(findOrder(b.dataset.edit));
  if(b.dataset.receipt)showReceipt(findOrder(b.dataset.receipt));
  if(b.dataset.status){b.disabled=true;try{await changeStatus(Number(b.dataset.id),b.dataset.status);}finally{b.disabled=false;}}
  if(b.dataset.settle){if(pendingMovement){await sendMovement();return;}const d=state.data.drivers.find(d=>d.id===Number(b.dataset.settle));const a=await ask('تسوية '+d.name,[{name:'amount',label:'موجب: استلام من الطيار / سالب: دفع للطيار',type:'number',value:d.balance}]);if(a)await sendMovement({amount:Number(a.amount),reason:'تسوية '+d.name,driver_id:d.id});}
  if(b.dataset.proof){const r=await fetch(base+'/api/pos/orders/'+b.dataset.proof+'/proof',{headers:{'X-Pos-Token':state.token}});if(!r.ok)throw new Error('تعذر عرض الإثبات');const url=URL.createObjectURL(await r.blob());$('#receipt').innerHTML=`<img src="${url}" style="max-width:100%">`;state.receipt=null;$('#receiptDialog').showModal();$('#receiptDialog').addEventListener('close',()=>URL.revokeObjectURL(url),{once:true});}
}));
window.addEventListener('beforeunload',e=>{if(state.pending||state.cart.length){e.preventDefault();e.returnValue='';}});
window.addEventListener('offline',()=>connection(false));window.addEventListener('online',refresh);
if(!window.BROOST_POS_DEVICE_KEY)$('#loginHint').textContent='ادخل كلمة مرور الأدمن لفتح الكاشير من المتصفح';
$('#login').showModal();setInterval(refresh,5000);

$('#clearCart').onclick=()=>run(async()=>{if(state.pending){notice('أكّد نتيجة الطلب المعلق قبل تفريغ السلة.');return;}if(!await ask('تفريغ السلة',[{name:'confirm',label:'تأكيد',options:[{value:'yes',label:'تفريغ السلة وإلغاء التعديل غير المحفوظ'}]}]))return;state.cart=[];state.editing=null;$('#checkout').reset();renderCart();notice('');});
