/* Cloud-only cashier: no IndexedDB, localStorage, SQLite or offline upload queue. */
const $ = q => document.querySelector(q);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const money = n => `${Number(n || 0).toLocaleString('ar-EG', { maximumFractionDigits: 2 })} ج`;
const statusNames = {
  NEW: 'جديد',
  PREPARING: 'جاري التجهيز',
  READY: 'جاهز',
  DISPATCHED: 'خرج للتوصيل',
  COMPLETED: 'مكتمل',
  CANCELLED: 'ملغي'
};
const state = { token: '', data: null, cart: [], receipt: null, offset: 0, pending: null, refreshing: false, busy: false, editing: null };
const terminal = window.BROOST_POS_TERMINAL_ID || sessionStorage.getItem('broost_terminal') || crypto.randomUUID();
if (!window.BROOST_POS_TERMINAL_ID) sessionStorage.setItem('broost_terminal', terminal);
const base = String(window.BROOST_CONFIG?.apiBaseUrl || '').replace(/\/$/, '');

function notice(text) {
  const el = $('#notice');
  if (!el) return;
  el.textContent = text;
  el.hidden = !text;
  if (text && typeof clearTimeout === 'function' && typeof setTimeout === 'function') {
    clearTimeout(el._timer);
    el._timer = setTimeout(() => { el.hidden = true; }, 5000);
  }
}

function connection(ok) {
  const el = $('#connection');
  if (!el) return;
  el.innerHTML = ok ? '<span class="dot"></span> متصل بالسيرفر' : '<span class="dot" style="background:#ef4444"></span> الاتصال متوقف';
  el.className = ok ? 'online' : 'offline';
}

async function api(path, method = 'GET', body) {
  let response;
  try {
    response = await fetch(base + path, {
      method,
      headers: {
        'Content-Type': 'application/json',
        'X-Pos-Token': state.token,
        'X-Pos-Terminal': terminal
      },
      body: body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(20000),
      cache: 'no-store'
    });
  } catch (error) {
    connection(false);
    throw new Error('تعذر تأكيد العملية. تأكد من الاتصال ثم أعد المحاولة؛ لا تُنشئ فاتورة بديلة.');
  }
  const data = await response.json().catch(() => ({}));
  if (response.status === 401) {
    if (!$('#login')?.open) $('#login')?.showModal?.();
  }
  if (!response.ok) {
    const error = new Error(typeof data.detail === 'string' ? data.detail : 'راجع البيانات المدخلة');
    error.status = response.status;
    throw error;
  }
  connection(true);
  return data;
}

async function run(fn) {
  try {
    await fn();
  } catch (e) {
    notice(e.message);
  }
}

async function refresh() {
  if (!state.token || state.refreshing) return;
  state.refreshing = true;
  try {
    const previousVersion = state.data?.menu.version;
    state.data = await api('/api/pos/state');
    if (previousVersion !== state.data.menu.version) renderMenu();
    renderAccounts();
    renderActive();
    totals();
    if ($('#orders') && !$('#orders').hidden) await loadHistory();
  } catch (e) {
    connection(false);
    notice(e.message);
  } finally {
    state.refreshing = false;
  }
}

let lastRenderedCategoryVersion = null;
function renderMenu() {
  if (!state.data?.menu) return;
  const m = state.data.menu, selected = $('#category')?.value || '', area = $('#area')?.value || '';
  
  // Update hidden select and chips only if categories or version changed
  if (lastRenderedCategoryVersion !== m.version) {
    lastRenderedCategoryVersion = m.version;
    if ($('#category')) {
      $('#category').innerHTML = '<option value="">كل الأقسام</option>' +
        m.categories.map(c => `<option value="${esc(c.sync_id)}">${esc(c.name)}</option>`).join('') +
        '<option value="offers">العروض</option>';
      $('#category').value = selected;
    }
    const chipsEl = $('#categoryChips');
    if (chipsEl) {
      chipsEl.innerHTML = `<button type="button" class="category-chip${!selected ? ' active' : ''}" data-cat="">الكل</button>` +
        m.categories.map(c => `<button type="button" class="category-chip${selected === c.sync_id ? ' active' : ''}" data-cat="${esc(c.sync_id)}">${esc(c.name)}</button>`).join('') +
        `<button type="button" class="category-chip${selected === 'offers' ? ' active' : ''}" data-cat="offers">العروض</button>`;
    }
  } else {
    document.querySelectorAll('.category-chip, .cat-chip').forEach(c => {
      c.classList.toggle('active', (c.dataset.cat || '') === selected);
    });
  }

  if ($('#area')) {
    $('#area').innerHTML = '<option value="">اختر المنطقة</option>' +
      state.data.areas.filter(a => a.is_active && a.delivery_enabled).map(a => `<option value="${a.id}">${esc(a.name)} — ${money(a.delivery_fee)}</option>`).join('');
    $('#area').value = area;
  }

  renderProducts();
}

function renderProducts() {
  const m = state.data?.menu;
  if (!m) return;
  const selected = $('#category')?.value || '';
  const query = ($('#search')?.value || '').trim();
  let items = m.items.filter(i => i.is_available && (!selected || i.category_sync_id === selected)).map(i => ({ ...i, kind: 'item' }));
  if (!selected || selected === 'offers') {
    items.push(...m.offers.filter(o => o.is_active).map(o => ({ ...o, base_price: o.offer_price, kind: 'offer' })));
  }

  if ($('#products')) {
    $('#products').innerHTML = items.filter(i => i.name.includes(query)).map(i => `
      <button type="button" class="product${i.kind === 'offer' ? ' offer-card' : ''}" data-product="${esc(i.sync_id)}" data-kind="${i.kind}">
        <div class="product-title">${esc(i.name)}</div>
        <div class="product-footer">
          <span class="product-price">${money(i.base_price)}</span>
        </div>
      </button>
    `).join('') || '<p style="grid-column:1/-1;text-align:center;padding:30px;color:var(--text-muted)">لا توجد أصناف مطابقة للبحث.</p>';
  }
}

let selectedItem = null;
function chooseItem(id, kind) {
  if (state.pending) {
    notice('يوجد طلب جارٍ تأكيده؛ أعد محاولة حفظه أولًا.');
    return;
  }
  const m = state.data?.menu;
  if (!m) return;
  const item = (kind === 'offer' ? m.offers : m.items).find(i => i.sync_id === id);
  if (!item) return;

  const sizes = kind === 'offer' ? [] : (m.sizes || []).filter(s => s.item_sync_id === id);
  const extras = kind === 'offer' ? [] : (m.extras || []).filter(e => e.item_sync_id === id);

  // If item has no sizes and no extras, add directly to cart! Instant 0ms response!
  if (sizes.length === 0 && extras.length === 0) {
    const existingIndex = state.cart.findIndex(c => 
      c.item_id === (kind === 'item' ? item.sync_id : null) &&
      c.offer_id === (kind === 'offer' ? item.sync_id : null) &&
      !c.spicy && (!c.extra_ids || c.extra_ids.length === 0) && !c.size_id
    );
    if (existingIndex >= 0) {
      state.cart[existingIndex].quantity += 1;
    } else {
      state.cart.push({
        name: item.name,
        size: 'عادي',
        unit_price: Number(kind === 'offer' ? item.offer_price : item.base_price),
        item_id: kind === 'item' ? item.sync_id : null,
        offer_id: kind === 'offer' ? item.sync_id : null,
        size_id: null,
        extra_ids: [],
        spicy: false,
        quantity: 1
      });
    }
    renderCart();
    return;
  }

  selectedItem = { item, kind };
  if ($('#itemName')) $('#itemName').textContent = item.name;
  if ($('#size')) {
    $('#size').innerHTML = '<option value="">عادي</option>' +
      sizes.map(s => `<option value="${esc(s.sync_id)}">${esc(s.name)} (+${money(s.price_offset)})</option>`).join('');
  }
  if ($('#extras')) {
    $('#extras').innerHTML = extras.map(e => `
      <label class="custom-checkbox">
        <input type="checkbox" value="${esc(e.sync_id)}">
        <span>${esc(e.name)} (+${money(e.price)})</span>
      </label>
    `).join('');
  }
  if ($('#spicy')) {
    $('#spicy').checked = false;
    $('#spicy').disabled = kind === 'offer';
  }
  if ($('#quantity')) $('#quantity').value = 1;
  if ($('#itemDialog')) $('#itemDialog').showModal();
}

if ($('#itemForm')) {
  $('#itemForm').onsubmit = e => {
    e.preventDefault();
    const { item, kind } = selectedItem, m = state.data.menu;
    const size = m.sizes.find(s => s.sync_id === $('#size').value);
    const extras = [...$('#extras').querySelectorAll('input:checked')].map(i => m.extras.find(x => x.sync_id === i.value));
    state.cart.push({
      name: item.name,
      size: size?.name || 'عادي',
      unit_price: Number(kind === 'offer' ? item.offer_price : item.base_price) + Number(size?.price_offset || 0) + extras.reduce((s, x) => s + Number(x.price), 0),
      item_id: kind === 'item' ? item.sync_id : null,
      offer_id: kind === 'offer' ? item.sync_id : null,
      size_id: size?.sync_id || null,
      extra_ids: extras.map(x => x.sync_id),
      spicy: $('#spicy').checked,
      quantity: Number($('#quantity').value)
    });
    $('#itemDialog').close();
    renderCart();
  };
}

function syncSegmented() {
  const fVal = $('#fulfillment')?.value || 'PICKUP';
  document.querySelectorAll('#fulfillmentPills .seg-item').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.val === fVal);
  });
  const pVal = $('#payment')?.value || 'CASH';
  document.querySelectorAll('#paymentPills .seg-item').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.val === pVal);
  });
}

function renderCart() {
  const isEditing = !!state.editing;
  if ($('#cartTitle')) $('#cartTitle').textContent = isEditing ? 'تعديل الفاتورة #' + state.editing.id : 'الفاتورة الحالية';
  if ($('#cartCountBadge')) $('#cartCountBadge').textContent = `${state.cart.reduce((sum, i) => sum + i.quantity, 0)} صنف`;
  
  if ($('#editBanner')) {
    $('#editBanner').hidden = !isEditing;
    if (isEditing && $('#editOrderId')) {
      $('#editOrderId').textContent = '#' + state.editing.id + (state.editing.public_number ? ` (${state.editing.public_number})` : '');
    }
  }

  if ($('#cartLines')) {
    $('#cartLines').innerHTML = state.cart.map((i, n) => `
      <div class="line">
        <div class="line-info">
          <div class="line-title">
            <span>${esc(i.name)}</span>
            ${i.spicy ? '<span class="spice-tag">حار</span>' : ''}
          </div>
          <div class="line-meta">${esc(i.size)} · ${i.quantity} × ${money(i.unit_price)}</div>
          <div class="line-price">${money(i.quantity * i.unit_price)}</div>
        </div>
        <div class="line-actions">
          <button type="button" class="qty-btn" data-qty-dec="${n}" ${state.pending ? 'disabled' : ''} title="تقليل">−</button>
          <span class="qty-val">${i.quantity}</span>
          <button type="button" class="qty-btn" data-qty-inc="${n}" ${state.pending ? 'disabled' : ''} title="زيادة">+</button>
          <button type="button" class="del-btn" data-remove="${n}" ${state.pending ? 'disabled' : ''}>حذف</button>
        </div>
      </div>
    `).join('') || '<p style="text-align:center;padding:24px 10px;color:var(--text-muted);font-size:13px">السلة فارغة. اضغط على الأصناف لإضافتها.</p>';
  }
  totals();
}

function totals() {
  const sub = state.cart.reduce((s, i) => s + i.quantity * i.unit_price, 0);
  const delivery = $('#fulfillment')?.value === 'DELIVERY';
  const fee = delivery ? Number(state.data?.areas?.find(a => a.id === Number($('#area')?.value))?.delivery_fee || 0) : 0;
  const discount = Number($('#discount')?.value || 0);
  const total = Math.max(0, sub + fee - discount);

  if ($('#areaLabel')) $('#areaLabel').hidden = !delivery;
  if ($('#addressLabel')) $('#addressLabel').hidden = !delivery;

  if ($('#totals')) {
    $('#totals').innerHTML = `
      <div>${money(total)}</div>
      <small>الأصناف: ${money(sub)}${delivery ? ' · التوصيل: ' + money(fee) : ''}${discount > 0 ? ' · الخصم: ' + money(discount) : ''}</small>
    `;
  }

  syncSegmented();

  if ($('#submitSale')) {
    $('#submitSale').disabled = state.busy || (!state.cart.length && !state.pending) || (!state.data?.shift && !state.pending);
    $('#submitSale').textContent = state.pending
      ? 'إعادة تأكيد نفس الفاتورة'
      : state.data?.shift
        ? (state.editing ? 'حفظ تعديل الفاتورة #' + state.editing.id : 'حفظ الفاتورة')
        : 'افتح الوردية أولًا';
  }

  $('#checkout')?.querySelectorAll('input,select').forEach(e => {
    e.disabled = !!state.pending;
  });
  if ($('#lookup')) $('#lookup').disabled = !!state.pending;
}

if ($('#checkout')) {
  $('#checkout').onsubmit = e => {
    e.preventDefault();
    return run(async () => {
      if (state.busy) return;
      if (!state.pending) {
        state.pending = {
          request_id: crypto.randomUUID(),
          edit_order_id: state.editing?.id || null,
          expected_revision: state.editing?.pos_revision ?? null,
          fulfillment: $('#fulfillment')?.value || 'PICKUP',
          payment_method: $('#payment')?.value || 'CASH',
          customer_name: $('#customerName')?.value || 'عميل المطعم',
          customer_phone: $('#phone')?.value || '',
          area_id: Number($('#area')?.value) || null,
          detailed_address: $('#address')?.value || '',
          discount: Number($('#discount')?.value || 0),
          cash_received: Number($('#cash')?.value || 0),
          notes: $('#notes')?.value || '',
          items: state.cart.map(({ item_id, offer_id, quantity, size_id, extra_ids, spicy }) => ({
            item_id, offer_id, quantity, size_id, extra_ids, spicy
          }))
        };
      }
      state.busy = true;
      totals();
      try {
        await api('/api/pos/draft', 'PUT', state.pending);
        const order = await api('/api/pos/orders', 'POST', state.pending);
        await api('/api/pos/draft?request_id=' + encodeURIComponent(state.pending.request_id), 'DELETE');
        state.pending = null;
        state.editing = null;
        state.cart = [];
        $('#checkout')?.reset?.();
        renderCart();
        notice(`تم حفظ الفاتورة #${order.id} بنجاح على السيرفر`);
        showReceipt(order);
        await refresh();
      } catch (error) {
        if (error.status >= 400 && error.status < 500 && error.status !== 401) {
          await api('/api/pos/draft?request_id=' + encodeURIComponent(state.pending.request_id), 'DELETE');
          state.pending = null;
        }
        throw error;
      } finally {
        state.busy = false;
        totals();
      }
    });
  };
}

function receiptHtml(order, kitchen = false) {
  const lines = order.items.map(i => `
    <tr>
      <td>${esc(i.item_name)}<br><small>${esc(i.size_name)} ${esc((i.extras || []).map(e => e.name).join('، '))}</small></td>
      <td>${i.quantity}</td>
      ${kitchen ? '' : `<td>${money(i.quantity * i.unit_price)}</td>`}
    </tr>
  `).join('');
  return `<html dir="rtl"><head><meta charset="utf-8"><style>body{font-family:Tahoma;text-align:center;font-size:12px}table{width:100%;border-collapse:collapse}td{padding:6px;border-bottom:1px solid #ddd}small{font-size:10px}h2{font-size:20px}</style></head><body><h2>بروست</h2><h3>${kitchen ? 'نسخة المطبخ' : 'فاتورة العميل'} #${order.id}</h3><p>${esc(order.public_number)}<br>${esc(order.created_at)}</p><p>${esc(order.customer_name)}<br>${esc(order.customer_phone)}<br>${esc(order.area_name)} ${esc(order.detailed_address)}</p><table>${lines}</table>${kitchen ? '' : `<p>الأصناف ${money(order.subtotal)}<br>الخصم ${money(order.discount)}<br>التوصيل ${money(order.delivery_fee)}</p><h2>الإجمالي ${money(order.total)}</h2><p>${esc({ CASH: 'نقدي', WALLET: 'محفظة', VISA: 'فيزا' }[order.payment_method])} · ${esc(statusNames[order.status])}</p><p>الباقي ${money(order.change_due)}</p>`}<p>${esc(order.notes)}</p><p>الكاشير: ${esc(order.cashier_name)}</p><p>0552802874 · 01092453841</p></body></html>`;
}

function showReceipt(order) {
  state.receipt = order;
  if ($('#receipt')) {
    const match = receiptHtml(order).match(/<body>([\s\S]*)<\/body>/);
    if (match) $('#receipt').innerHTML = match[1];
  }
  if (!$('#receiptDialog')?.open) $('#receiptDialog')?.showModal?.();
}

async function printReceipt(kitchen) {
  if (!state.receipt) return;
  const html = receiptHtml(state.receipt, kitchen);
  if (window.broostPrinter) {
    window.broostPrinter.printHtml(html);
    return;
  }
  const match = html.match(/<body>([\s\S]*)<\/body>/);
  if ($('#receipt') && match) $('#receipt').innerHTML = match[1];
  window.print();
}

function orderCard(o) {
  const badgeClass = (o.status || '').toLowerCase();
  const canEdit = o.status !== 'CANCELLED';
  const isDelivery = o.fulfillment === 'DELIVERY';

  return `
    <article class="order-card" data-order-card="${o.id}">
      <div class="order-card-header">
        <div>
          <span class="order-card-title">#${o.id} ${esc(o.public_number ? '(' + o.public_number + ')' : '')}</span>
          <span class="order-card-source">${o.source === 'POS' ? 'صالة' : 'أونلاين'}</span>
        </div>
        <div style="display:flex;align-items:center;gap:8px">
          <span class="order-badge ${badgeClass}">${esc(statusNames[o.status] || o.status)}</span>
          <strong class="order-card-total">${money(o.total)}</strong>
        </div>
      </div>

      <div class="order-card-body">
        <p>
          <b>${esc(o.customer_name)}</b> ${o.customer_phone ? '· ' + esc(o.customer_phone) : ''}
          ${isDelivery ? `<br>توصيل: ${esc(o.area_name || '')} ${esc(o.detailed_address || '')}` : '<br>صالة / سفري'}
          ${o.notes ? `<br><small style="color:var(--accent-amber)">ملاحظة: ${esc(o.notes)}</small>` : ''}
        </p>
        <div class="order-items-snippet">
          ${o.items.map(i => `${i.quantity} × ${esc(i.item_name)}${i.size_name ? ' (' + esc(i.size_name) + ')' : ''}`).join(' · ')}
        </div>
      </div>

      <div class="order-card-actions">
        <button type="button" data-receipt="${o.id}">طباعة</button>
        ${canEdit ? `<button type="button" class="btn-edit" data-edit="${o.id}">تعديل الطلب</button>` : ''}
        ${o.has_payment_proof ? `<button type="button" data-proof="${o.id}">إثبات التحويل</button>` : ''}
        ${o.status === 'NEW' ? `<button type="button" data-status="PREPARING" data-id="${o.id}">قبول وتجهيز</button>` : ''}
        ${o.status === 'PREPARING' && !isDelivery ? `<button type="button" data-status="READY" data-id="${o.id}">جاهز للاستلام</button>` : ''}
        ${['PREPARING', 'READY'].includes(o.status) && isDelivery ? `<button type="button" class="btn-dispatch" data-status="DISPATCHED" data-id="${o.id}">خروج للتوصيل</button>` : ''}
        ${(o.status === 'DISPATCHED' || (!isDelivery && ['PREPARING', 'READY'].includes(o.status))) ? `<button type="button" class="btn-complete" data-status="COMPLETED" data-id="${o.id}">تم التسليم</button>` : ''}
        ${o.status !== 'CANCELLED' ? `<button type="button" data-status="CANCELLED" data-id="${o.id}" style="color:#dc2626">إلغاء الطلب</button>` : ''}
      </div>
    </article>
  `;
}

function renderActive() {
  const activeList = (state.data?.orders || []).filter(o => o.status !== 'COMPLETED' && o.status !== 'CANCELLED');
  const count = activeList.length;
  if ($('#activeBadge')) {
    $('#activeBadge').textContent = String(count);
    $('#activeBadge').classList?.toggle?.('has-active', count > 0);
  }
  const btn = document.querySelector?.('.live-orders-btn');
  if (btn) btn.classList?.toggle?.('has-orders', count > 0);
  
  const html = activeList.map(orderCard).join('') || '<p style="grid-column:1/-1;text-align:center;padding:40px;color:var(--text-muted)">لا توجد طلبات جارية قيد التنفيذ حالياً.</p>';
  if ($('#activeOrders')) $('#activeOrders').innerHTML = html;
}

let history = [];
async function loadHistory() {
  history = await api('/api/pos/history?offset=' + state.offset);
  if ($('#history')) {
    $('#history').innerHTML = history.map(orderCard).join('') || '<p style="grid-column:1/-1;text-align:center;padding:40px;color:var(--text-muted)">لا توجد فواتير محفوظة في السجل.</p>';
  }
  if ($('#previous')) $('#previous').disabled = state.offset === 0;
  if ($('#next')) $('#next').disabled = history.length < 100;
}

function findOrder(id) {
  return [...(state.data?.orders || []), ...history].find(o => o.id === Number(id));
}

function ask(title, fields) {
  return new Promise(resolve => {
    if ($('#inputTitle')) $('#inputTitle').textContent = title;
    if ($('#inputFields')) {
      $('#inputFields').innerHTML = fields.map(f => `
        <div class="field-group">
          <label>${esc(f.label)}</label>
          ${f.options ? `
            <select name="${f.name}">
              ${f.options.map(o => `<option value="${esc(o.value)}">${esc(o.label)}</option>`).join('')}
            </select>
          ` : `
            <input name="${f.name}" type="${f.type || 'text'}" value="${esc(f.value || '')}" ${f.type === 'number' ? 'step="0.01"' : ''} required>
          `}
        </div>
      `).join('');
    }
    const d = $('#inputDialog');
    let done = false;
    if (!d) { resolve(null); return; }
    d.onclose = () => { if (!done) resolve(null); };
    if ($('#inputForm')) {
      $('#inputForm').onsubmit = e => {
        e.preventDefault();
        done = true;
        const data = Object.fromEntries(new FormData(e.target));
        d.close();
        resolve(data);
      };
    }
    d.showModal();
  });
}

async function changeStatus(id, status) {
  const order = findOrder(id);
  if (!order) return;
  let payment_status = null;
  
  if (status === 'CANCELLED') {
    if (!await ask('تأكيد إلغاء الفاتورة #' + id, [{ name: 'confirm', label: 'تأكيد الإلغاء', options: [{ value: 'yes', label: 'نعم، إلغاء الفاتورة' }] }])) {
      return;
    }
  }

  // Delivery status changed without asking for drivers!
  if (status === 'DISPATCHED') {
    await api('/api/pos/orders/' + id, 'PATCH', { status });
    notice(`تم تغيير حالة الطلب #${id} إلى: خرج للتوصيل`);
    await refresh();
    await loadHistory();
    return;
  }

  if (order.payment_method === 'WALLET' && order.payment_status === 'PROOF_UPLOADED' && status === 'PREPARING') {
    if (!await ask('تأكيد استلام التحويل', [{ name: 'confirm', label: 'بعد مراجعة الإثبات', options: [{ value: 'yes', label: 'تم استلام المبلغ' }] }])) return;
    payment_status = 'CONFIRMED';
  }

  await api('/api/pos/orders/' + id, 'PATCH', { status, payment_status });
  notice(`تم تحديث الفاتورة #${id} بنجاح`);
  await refresh();
  await loadHistory();
}

async function editOrder(order) {
  if (state.pending) {
    notice('أكّد نتيجة الطلب المعلق أولًا.');
    return;
  }
  if (state.cart.length > 0) {
    const confirmOverwrite = await ask('تعديل الفاتورة #' + order.id, [
      { name: 'confirm', label: 'تنبيه: السلة الحالية تحتوي على أصناف', options: [{ value: 'yes', label: 'إلغاء السلة الحالية والبدء في تعديل الفاتورة' }] }
    ]);
    if (!confirmOverwrite) return;
  }

  const m = state.data?.menu;
  if (!m) return;
  const cart = order.items.map(line => {
    const item = m.items.find(i => i.sync_id === line.menu_item_sync_id);
    const offer = !item && m.offers.find(o => 'عرض: ' + o.name === line.item_name);
    if (!item && !offer) throw new Error('الصنف لم يعد موجودًا في المنيو؛ راجع الإدارة قبل تعديل الفاتورة.');
    const size = item && m.sizes.find(s => s.item_sync_id === item.sync_id && s.name === line.size_name);
    const extras = item ? m.extras.filter(e => e.item_sync_id === item.sync_id && (line.extras || []).some(x => x.name === e.name)) : [];
    return {
      name: item?.name || offer.name,
      size: size?.name || 'عادي',
      unit_price: Number(item?.base_price ?? offer.offer_price) + Number(size?.price_offset || 0) + extras.reduce((a, e) => a + Number(e.price), 0),
      item_id: item?.sync_id || null,
      offer_id: offer?.sync_id || null,
      size_id: size?.sync_id || null,
      extra_ids: extras.map(e => e.sync_id),
      spicy: (line.extras || []).some(e => e.system_key === 'spicy'),
      quantity: line.quantity
    };
  });

  state.editing = order;
  state.cart = cart;

  for (const [id, value] of Object.entries({
    fulfillment: order.fulfillment || 'PICKUP',
    payment: order.payment_method || 'CASH',
    customerName: order.customer_name || '',
    phone: order.customer_phone || '',
    area: order.area_id || '',
    address: order.detailed_address || '',
    discount: order.discount || 0,
    cash: order.cash_received || 0,
    notes: order.notes || ''
  })) {
    if ($('#' + id)) $('#' + id).value = value;
  }

  // Switch to sale tab
  document.querySelectorAll('.tab').forEach(t => { t.hidden = t.id !== 'sale'; });
  document.querySelectorAll('nav [data-tab]').forEach(t => { t.classList.toggle('active', t.dataset.tab === 'sale'); });
  renderCart();
  syncSegmented();
  notice(`أنت الآن في وضع تعديل الفاتورة #${order.id} — يمكنك إضافة أو حذف أصناف ثم حفظ الفاتورة.`);
}

function renderAccounts() {
  const shift = state.data?.shift;
  if ($('#shiftBadge')) {
    $('#shiftBadge').textContent = shift ? `الوردية #${shift.id} مفتوحة` : 'لا توجد وردية مفتوحة';
  }
  if ($('#shift')) {
    $('#shift').innerHTML = shift ? `
      <div class="metric-card">
        <div class="metric-label">النقد المتوقع في الدرج</div>
        <div class="metric-val highlight">${money(shift.expected_cash)}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">إجمالي مبيعات الوردية</div>
        <div class="metric-val">${money(shift.sales)}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">عدد الفواتير</div>
        <div class="metric-val">${shift.invoices || 0} فاتورة</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">عهدة بداية الوردية</div>
        <div class="metric-val">${money(shift.opening_cash || 0)}</div>
      </div>
    ` : '<div style="grid-column:1/-1;text-align:center;padding:30px;color:var(--text-muted)">لا توجد وردية مفتوحة حالياً. اضغط "فتح وردية" لبدء البيع.</div>';
  }
  if ($('#openShift')) $('#openShift').disabled = !!shift;
  if ($('#closeShift')) $('#closeShift').disabled = !shift;
  if ($('#movement')) $('#movement').disabled = !shift;
}

async function loadShifts() {
  const rows = await api('/api/pos/shifts');
  if ($('#shifts')) {
    $('#shifts').innerHTML = `
      <table>
        <thead>
          <tr>
            <th>رقم الوردية</th>
            <th>الحالة والوقت</th>
            <th>المبيعات</th>
            <th>النقد المتوقع</th>
            <th>النقد الفعلي</th>
            <th>فرق العهدة</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map(s => `
            <tr>
              <td><b>#${s.id}</b></td>
              <td>${esc(s.opened_at)} <span class="order-badge ${s.closed_at ? 'completed' : 'new'}">${s.closed_at ? 'مغلقة' : 'مفتوحة'}</span></td>
              <td>${money(s.sales)}</td>
              <td><b>${money(s.expected_cash)}</b></td>
              <td>${s.actual_cash === null ? '—' : money(s.actual_cash)}</td>
              <td style="color:${(s.actual_cash - s.expected_cash) < 0 ? '#f87171' : '#34d399'}">
                ${s.actual_cash === null ? '—' : (s.actual_cash - s.expected_cash >= 0 ? '+' : '') + money(s.actual_cash - s.expected_cash)}
              </td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
  }
}

if ($('#openShift')) {
  $('#openShift').onclick = () => run(async () => {
    const a = await ask('فتح وردية جديدة', [{ name: 'cash', label: 'عهدة البداية في الدرج (ج.م)', type: 'number', value: '0' }]);
    if (a) {
      await api('/api/pos/shifts', 'POST', { opening_cash: Number(a.cash) });
      await refresh();
      await loadShifts();
      notice('✅ تم فتح الوردية بنجاح! يمكنك الآن تسجيل الطلبات.');
    }
  });
}

if ($('#closeShift')) {
  $('#closeShift').onclick = () => run(async () => {
    const a = await ask('إغلاق الوردية الحالية', [{ name: 'cash', label: 'المبلغ الفعلي الموجود بالدرج بعد الجرد (ج.م)', type: 'number', value: state.data?.shift?.expected_cash || 0 }]);
    if (a) {
      await api('/api/pos/shifts/' + state.data.shift.id + '/close', 'POST', { actual_cash: Number(a.cash) });
      await refresh();
      await loadShifts();
      notice('🔒 تم إغلاق الوردية بنجاح.');
    }
  });
}

let pendingMovement = null;
async function sendMovement(data) {
  if (!pendingMovement) pendingMovement = { request_id: crypto.randomUUID(), ...data };
  await api('/api/pos/movements', 'POST', pendingMovement);
  pendingMovement = null;
  await refresh();
  await loadShifts();
  notice('تم تسجيل الحركة بنجاح.');
}

if ($('#movement')) {
  $('#movement').onclick = () => run(async () => {
    if (pendingMovement) { await sendMovement(); return; }
    const a = await ask('تسجيل حركة خزينة (مصروف أو إيداع)', [
      { name: 'amount', label: 'المبلغ: سالب للمصروف (مثل -50)، موجب للإيداع (مثل 100)', type: 'number' },
      { name: 'reason', label: 'البيان والسبب' }
    ]);
    if (a) await sendMovement({ amount: Number(a.amount), reason: a.reason });
  });
}

if ($('#lookup')) {
  $('#lookup').onclick = () => run(async () => {
    const phoneVal = $('#phone')?.value?.trim();
    if (!phoneVal) { notice('ادخل رقم الموبايل أولًا للبحث.'); return; }
    const orders = await api('/api/pos/customers?phone=' + encodeURIComponent(phoneVal));
    if (!orders.length) {
      notice('لا يوجد سجل طلبات سابق لهذا الرقم.');
      return;
    }
    const o = orders[0];
    if ($('#customerName')) $('#customerName').value = o.customer_name || '';
    if ($('#address')) $('#address').value = o.detailed_address || '';
    if ($('#area')) $('#area').value = o.area_id || '';
    notice(`تم العثور على بيانات العميل: ${o.customer_name} (آخر طلب #${o.id})`);
    totals();
  });
}

if ($('#loginForm')) {
  $('#loginForm').onsubmit = e => {
    e.preventDefault();
    run(async () => {
      try {
        const response = await fetch(base + '/api/pos/login', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Sync-Key': window.BROOST_POS_DEVICE_KEY || ''
          },
          body: JSON.stringify({ pin: $('#pin').value }),
          signal: AbortSignal.timeout(20000)
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'تعذر تسجيل الدخول');
        state.token = data.token;
        if ($('#pin')) $('#pin').value = '';
        if ($('#login')) $('#login').close();
        await refresh();
        state.pending = await api('/api/pos/draft');
        totals();
        notice(state.pending
          ? '⚠️ يوجد طلب معلق لم تكتمل عملية حفظه. اضغط "إعادة تأكيد نفس الفاتورة" للمتابعة.'
          : 'أهلًا بك! افتح الوردية من «إدارة الوردية» لبدء البيع.');
      } catch (err) {
        if ($('#loginError')) $('#loginError').textContent = err.message;
      }
    });
  };
}

if ($('#logout')) {
  $('#logout').onclick = () => {
    if (state.pending || state.cart.length) {
      notice('أكمل الفاتورة الحالية قبل تسجيل الخروج.');
      return;
    }
    state.token = '';
    if ($('#login')) $('#login').showModal();
  };
}

if ($('#admin')) {
  $('#admin').onclick = () => window.open('https://broost-three.vercel.app/admin', '_blank');
}

if ($('#search')) {
  $('#search').oninput = () => {
    if ($('#clearSearch')) $('#clearSearch').hidden = !$('#search').value;
    if (state.data) renderProducts();
  };
}

if ($('#clearSearch')) {
  $('#clearSearch').onclick = () => {
    if ($('#search')) $('#search').value = '';
    $('#clearSearch').hidden = true;
    if (state.data) renderProducts();
  };
}

if ($('#category')) {
  $('#category').onchange = () => {
    const cat = $('#category').value;
    document.querySelectorAll('.category-chip, .cat-chip').forEach(c => {
      c.classList.toggle('active', (c.dataset.cat || '') === cat);
    });
    renderProducts();
  };
}

for (const selector of ['#fulfillment', '#area', '#discount', '#cash', '#payment']) {
  if ($(selector)) $(selector).oninput = totals;
}

if ($('#refreshOrders')) {
  $('#refreshOrders').onclick = () => run(loadHistory);
}
if ($('#refreshActive')) {
  $('#refreshActive').onclick = () => run(refresh);
}
if ($('#previous')) {
  $('#previous').onclick = () => run(async () => { state.offset = Math.max(0, state.offset - 100); await loadHistory(); });
}
if ($('#next')) {
  $('#next').onclick = () => run(async () => { state.offset += 100; await loadHistory(); });
}

if ($('#printReceipt')) $('#printReceipt').onclick = () => printReceipt(false);
if ($('#printKitchen')) $('#printKitchen').onclick = () => printKitchen(true);

if ($('#clearCart')) {
  $('#clearCart').onclick = () => run(async () => {
    if (state.pending) {
      notice('أكّد نتيجة الطلب المعلق قبل تفريغ السلة.');
      return;
    }
    if (!state.cart.length && !state.editing) return;
    if (!await ask('تفريغ السلة', [{ name: 'confirm', label: 'تأكيد', options: [{ value: 'yes', label: 'تفريغ السلة والعودة لطلب جديد' }] }])) return;
    state.cart = [];
    state.editing = null;
    $('#checkout')?.reset?.();
    renderCart();
    syncSegmented();
    notice('تم تفريغ السلة.');
  });
}

if ($('#cancelEdit')) {
  $('#cancelEdit').onclick = () => {
    state.editing = null;
    state.cart = [];
    $('#checkout')?.reset?.();
    renderCart();
    syncSegmented();
    notice('تم إلغاء وضع تعديل الفاتورة.');
  };
}

if ($('#itemQtyInc')) {
  $('#itemQtyInc').onclick = () => {
    if ($('#quantity')) $('#quantity').value = Math.min(50, Number($('#quantity').value) + 1);
  };
}
if ($('#itemQtyDec')) {
  $('#itemQtyDec').onclick = () => {
    if ($('#quantity')) $('#quantity').value = Math.max(1, Number($('#quantity').value) - 1);
  };
}

// Global Click Delegation
document.addEventListener('click', e => run(async () => {
  const b = e.target.closest('button');
  if (!b) return;

  if (b.dataset.close) {
    const dialog = $('#' + b.dataset.close);
    if (dialog) dialog.close();
  }

  if (b.dataset.product) {
    chooseItem(b.dataset.product, b.dataset.kind);
  }

  // Segmented Buttons (Fulfillment & Payment)
  if (b.classList.contains('seg-item')) {
    const group = b.closest('.segmented-group');
    if (group) {
      group.querySelectorAll('.seg-item').forEach(item => item.classList.remove('active'));
      b.classList.add('active');
      if (group.id === 'fulfillmentPills' && $('#fulfillment')) {
        $('#fulfillment').value = b.dataset.val;
        totals();
      }
      if (group.id === 'paymentPills' && $('#payment')) {
        $('#payment').value = b.dataset.val;
        totals();
      }
    }
  }

  // Category Chips
  if (b.classList.contains('category-chip') || b.classList.contains('cat-chip')) {
    const cat = b.dataset.cat || '';
    if ($('#category')) $('#category').value = cat;
    document.querySelectorAll('.category-chip, .cat-chip').forEach(c => {
      c.classList.toggle('active', (c.dataset.cat || '') === cat);
    });
    renderProducts();
  }

  // Cart Item Quantity Stepper
  if (b.dataset.qtyInc !== undefined && !state.pending) {
    const idx = Number(b.dataset.qtyInc);
    if (state.cart[idx]) {
      state.cart[idx].quantity += 1;
      renderCart();
    }
  }

  if (b.dataset.qtyDec !== undefined && !state.pending) {
    const idx = Number(b.dataset.qtyDec);
    if (state.cart[idx]) {
      if (state.cart[idx].quantity > 1) {
        state.cart[idx].quantity -= 1;
        renderCart();
      } else {
        state.cart.splice(idx, 1);
        renderCart();
      }
    }
  }

  if (b.dataset.remove !== undefined && !state.pending) {
    state.cart.splice(Number(b.dataset.remove), 1);
    renderCart();
  }

  // Tab Navigation
  if (b.dataset.tab) {
    document.querySelectorAll('.tab').forEach(t => {
      t.hidden = (t.id !== b.dataset.tab);
    });
    document.querySelectorAll('nav [data-tab]').forEach(t => {
      t.classList.toggle('active', t === b);
    });
    if (b.dataset.tab === 'activeTab') renderActive();
    if (b.dataset.tab === 'orders') await loadHistory();
    if (b.dataset.tab === 'accounts') await loadShifts();
  }

  // Edit Order
  if (b.dataset.edit) {
    editOrder(findOrder(b.dataset.edit));
  }

  // Receipt Details
  if (b.dataset.receipt) {
    showReceipt(findOrder(b.dataset.receipt));
  }

  // Status Change
  if (b.dataset.status) {
    b.disabled = true;
    try {
      await changeStatus(Number(b.dataset.id), b.dataset.status);
    } finally {
      b.disabled = false;
    }
  }

  // Payment Proof
  if (b.dataset.proof) {
    const r = await fetch(base + '/api/pos/orders/' + b.dataset.proof + '/proof', {
      headers: { 'X-Pos-Token': state.token }
    });
    if (!r.ok) throw new Error('تعذر عرض صورة الإثبات');
    const url = URL.createObjectURL(await r.blob());
    if ($('#receipt')) $('#receipt').innerHTML = `<img src="${url}" style="max-width:100%;border-radius:12px">`;
    state.receipt = null;
    if ($('#receiptDialog')) {
      $('#receiptDialog').showModal();
      $('#receiptDialog').addEventListener('close', () => URL.revokeObjectURL(url), { once: true });
    }
  }
}));

window.addEventListener('beforeunload', e => {
  if (state.pending || state.cart.length) {
    e.preventDefault();
    e.returnValue = '';
  }
});

window.addEventListener('offline', () => connection(false));
window.addEventListener('online', refresh);

if (!window.BROOST_POS_DEVICE_KEY && $('#loginHint')) {
  $('#loginHint').textContent = 'ادخل كلمة مرور الأدمن لفتح الكاشير من المتصفح';
}

if ($('#login')) $('#login').showModal();
setInterval(refresh, 5000);
