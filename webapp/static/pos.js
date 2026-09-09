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
const state = { token: '', data: null, cart: [], receipt: null, offset: 0, pending: null, refreshing: false, busy: false, editing: null, historyFilter: 'ALL', historySearch: '', daySummary: null };
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

let knownOnlineOrderIds = null;
let activeAlertOrder = null;
let titleFlashTimer = null;
let originalDocTitle = typeof document !== 'undefined' ? document.title : '';

function playNewOrderSound() {
  try {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (AudioCtx) {
      if (!window._posAudioCtx) window._posAudioCtx = new AudioCtx();
      const ctx = window._posAudioCtx;
      if (ctx.state === 'suspended' && typeof ctx.resume === 'function') {
        ctx.resume().catch(() => {});
      }
      const playTone = (freq, start, duration, type = 'sine', gainVal = 0.35) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = type;
        osc.frequency.setValueAtTime(freq, ctx.currentTime + start);
        gain.gain.setValueAtTime(gainVal, ctx.currentTime + start);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + start + duration);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(ctx.currentTime + start);
        osc.stop(ctx.currentTime + start + duration);
      };

      // Crisp, loud, pleasant two-cycle restaurant chime (Ding-Dong-Ding)
      playTone(587.33, 0.00, 0.30, 'triangle', 0.45); // D5
      playTone(880.00, 0.14, 0.40, 'sine', 0.55);    // A5
      playTone(1174.66, 0.28, 0.55, 'sine', 0.65);   // D6

      playTone(587.33, 0.65, 0.30, 'triangle', 0.45);
      playTone(880.00, 0.79, 0.40, 'sine', 0.55);
      playTone(1174.66, 0.93, 0.75, 'sine', 0.65);
    }
  } catch {
    /* ignore audio error */
  }

  // Native desktop app beep bridge if available
  try {
    if (window.broostPrinter && typeof window.broostPrinter.playAlert === 'function') {
      window.broostPrinter.playAlert();
    }
  } catch {
    /* ignore */
  }
}

function flashTitle(active) {
  if (typeof document === 'undefined') return;
  if (!originalDocTitle) originalDocTitle = document.title || 'بروست — الكاشير السحابي';
  if (titleFlashTimer) {
    clearInterval(titleFlashTimer);
    titleFlashTimer = null;
  }
  if (!active) {
    document.title = originalDocTitle;
    return;
  }
  let step = 0;
  titleFlashTimer = setInterval(() => {
    document.title = (step++ % 2 === 0) ? '🔔 طلب أونلاين جديد!' : originalDocTitle;
  }, 1000);
}

function showOnlineOrderAlert(order) {
  if (!order) return;
  activeAlertOrder = order;
  const alertEl = $('#onlineOrderAlert');
  if (!alertEl) return;

  const numEl = $('#alertOrderNumber');
  if (numEl) numEl.textContent = `#${order.id}`;

  const fulfillEl = $('#alertOrderFulfillment');
  if (fulfillEl) {
    fulfillEl.textContent = order.fulfillment === 'DELIVERY' ? 'دليفري' : 'استلام من المطعم';
    if (fulfillEl.style) {
      fulfillEl.style.color = order.fulfillment === 'DELIVERY' ? '#1d4ed8' : '#047857';
      fulfillEl.style.background = order.fulfillment === 'DELIVERY' ? '#dbeafe' : '#d1fae5';
    }
  }

  const custEl = $('#alertCustomerName');
  if (custEl) custEl.textContent = order.customer_name || 'عميل أونلاين';

  const totalEl = $('#alertOrderTotal');
  if (totalEl) totalEl.textContent = `${Number(order.total || 0).toFixed(2)} ج.م`;

  alertEl.hidden = false;
  playNewOrderSound();
  flashTitle(true);
}

function hideOnlineOrderAlert() {
  activeAlertOrder = null;
  const alertEl = $('#onlineOrderAlert');
  if (alertEl) alertEl.hidden = true;
  flashTitle(false);
}

function checkIncomingOnlineOrders() {
  const currentOrders = state.data?.orders || [];
  const newOnlineOrders = currentOrders.filter(o => o.source === 'ONLINE' && o.status === 'NEW');
  const hasNewOnline = newOnlineOrders.length > 0;

  // Toggle glowing pulse on the live orders button
  const liveBtn = document.querySelector?.('.live-orders-btn');
  if (liveBtn) {
    liveBtn.classList.toggle('has-new-online', hasNewOnline);
  }

  if (knownOnlineOrderIds === null) {
    // Initial load: remember all currently known IDs
    knownOnlineOrderIds = new Set(currentOrders.map(o => o.id));
    if (newOnlineOrders.length > 0) {
      showOnlineOrderAlert(newOnlineOrders[0]);
    }
    return;
  }

  // Find newly arrived online orders
  const newlyArrived = newOnlineOrders.filter(o => !knownOnlineOrderIds.has(o.id));
  newOnlineOrders.forEach(o => knownOnlineOrderIds.add(o.id));

  if (newlyArrived.length > 0) {
    showOnlineOrderAlert(newlyArrived[0]);
  } else if (!hasNewOnline && activeAlertOrder) {
    hideOnlineOrderAlert();
  }
}

try {
  if (typeof document?.addEventListener === 'function') {
    document.addEventListener('click', () => {
      if (window._posAudioCtx && window._posAudioCtx.state === 'suspended') {
        window._posAudioCtx.resume().catch(() => {});
      }
    }, { once: false });
  }
} catch { /* ignore */ }

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
    checkIncomingOnlineOrders();
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

const QR_DATA_URL = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAJYAAACWAQAAAAAUekxPAAAB70lEQVR42rVWQWobQRCs1gh2b70f8Iz8jMAqK8iLfAisISAZAutHOTD2CvyK4B3lA7O3EUiqXHIKOgRa6WMzFD3V1dUNGCLw75gWV579c44i0szAUUTWm1eRBUx4CCSaua7I6L47cjLhLUFR5IbPeNg4IN3b8OA9VJHJ0rvoxkmSjb+rNQMAmxn9c7vpzHgLCDMaFFTDwIhwsdaXBAroAGCPs0A+TJz+0SS2LGjdTTTZiDSVyK4bjusQVsb/hmnWWYHqeH50Q5vubRoKaVJFrkpfRXfqJh9M/xUv0ww0fAa+Llv8evPJxJ+8JYQm42Eu76c90mer/q7l7lYhMYhqDbiBHwvjXMqkmrWg4jiSvNg4RZgCmRX9tsAxhmTTJDyQFayG0ncntGKu7xI0U1nQA9148WL2odzIXGOrsfuxXsAbZ+aQmhySPuG4wcadDkZNXp3zjnOYga0wYv9pcbeyaohkJlAxtnZOl/ApCFFqAO/HJbyNU/E4gELZ1seXPdzP+4uRU5m0UVTyWNwYzyt/gN3HleQOjiOtuxEegGquSjWM0Y1Wn4QPpObMYWCE4//Z3RRFSHioy248C8ItvHMOokP9+q1tkVa3uF9YUJGnLvpg3LUQZgB1j6f1l+jeDoC959Bq2MGN0V2sPb/xvWuJ39uAHDHPzrgvAAAAAElFTkSuQmCC';

function receiptHtml(order, kitchen = false) {
  const isDelivery = order.fulfillment === 'DELIVERY';
  const invoiceNumber = `#${order.id}`;

  if (kitchen) {
    const kitchenItemsHtml = (order.items || []).map(i => {
      const extList = (i.extras || []).map(e => (typeof e === 'object' ? e.name : e)).filter(Boolean);
      const hasSpicy = (i.extras || []).some(e => e.system_key === 'spicy' || (e.name && e.name.includes('حار'))) || (i.item_name && i.item_name.includes('حار'));
      const spicyBadge = hasSpicy ? ' <span class="spicy">[حار]</span>' : '';
      const extHtml = extList.length ? `<div class="extras">+ إضافات: ${esc(extList.join('، '))}</div>` : '';
      return `
        <tr class="item-row">
          <td align="left" width="25%" class="item-qty">x${i.quantity}</td>
          <td align="right" width="75%">
            <span class="item-name">${esc(i.item_name)}${i.size_name && i.size_name !== 'عادي' ? ' (' + esc(i.size_name) + ')' : ''}</span>${spicyBadge}
            ${extHtml}
          </td>
        </tr>
      `;
    }).join('');

    return `
      <html dir="rtl">
      <head>
        <meta charset="utf-8">
        <style>
          @media print {
            @page { margin: 0; size: 80mm auto; }
            body { margin: 0; padding: 4px 6px; }
          }
          body {
            font-family: 'Cairo', 'Segoe UI', Tahoma, Arial, sans-serif;
            direction: rtl;
            text-align: right;
            margin: 0 auto;
            padding: 6px;
            width: 72mm;
            max-width: 72mm;
            color: #000;
            background: #fff;
            font-weight: bold;
            font-size: 12px;
            line-height: 1.5;
          }
          .receipt-container { width: 100%; margin: 0 auto; }
          .center { text-align: center; }
          .bold { font-weight: bold; }
          .title { font-size: 17px; font-weight: 900; margin: 2px 0; color: #000; }
          .subtitle { font-size: 13px; font-weight: bold; margin: 2px 0; color: #000; }
          .kitchen-id {
            font-size: 18px;
            font-weight: 900;
            border: 2px solid #000;
            padding: 4px 8px;
            margin: 6px 0;
            text-align: center;
            background: #fff;
          }
          .kitchen-channel { font-size: 13px; font-weight: 800; margin-bottom: 4px; color: #000; }
          .info-table { width: 100%; border-collapse: collapse; margin: 6px 0; font-size: 11.5px; line-height: 1.5; }
          .info-table td { padding: 2px 0; color: #000; }
          .items-table { width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 12.5px; }
          .items-table th { border-bottom: 1.5px solid #000; padding: 4px 0; font-weight: bold; font-size: 12px; color: #000; }
          .items-table td { padding: 5px 0; vertical-align: top; color: #000; }
          .item-qty { font-size: 15px; font-weight: 900; color: #000; }
          .item-name { font-weight: bold; }
          .spicy { color: #000; font-weight: 900; }
          .extras { font-size: 10.5px; padding-right: 6px; margin-top: 2px; color: #222; }
          .notes-box {
            border: 1.5px solid #000;
            padding: 6px;
            margin: 6px 0;
            font-size: 11.5px;
            font-weight: 900;
            background: #fff;
            text-align: right;
            line-height: 1.4;
          }
        </style>
      </head>
      <body>
        <div class="receipt-container">
          <div class="center">
            <div class="title">بروست — BROOST</div>
            <div class="subtitle">نسخة المطبخ</div>
            <div class="kitchen-id">طلب رقم ${invoiceNumber}</div>
            <div class="kitchen-channel">${isDelivery ? 'دليفري توصيل' : 'صالة / تيك أواي'}</div>
          </div>
          <table class="info-table">
            <tr><td align="left" width="60%">${esc(order.created_at || '')}</td><td class="bold" align="right" width="40%">التاريخ:</td></tr>
            ${isDelivery && order.customer_name && order.customer_name !== 'عميل المطعم' ? `<tr><td align="left" width="60%">${esc(order.customer_name)}</td><td class="bold" align="right" width="40%">العميل:</td></tr>` : ''}
            ${isDelivery && order.customer_phone ? `<tr><td align="left" width="60%" dir="ltr" style="text-align:left">${esc(order.customer_phone)}</td><td class="bold" align="right" width="40%">التليفون:</td></tr>` : ''}
            ${isDelivery && (order.area_name || order.detailed_address) ? `<tr><td align="left" width="60%">${esc(order.area_name || '')} ${esc(order.detailed_address || '')}</td><td class="bold" align="right" width="40%">العنوان:</td></tr>` : ''}
          </table>
          ${order.notes ? `<div class="notes-box">⚠️ تنبيه للمطبخ:<br/>${esc(order.notes)}</div>` : ''}
          <table class="items-table">
            <tr>
              <th align="left" width="25%">الكمية</th>
              <th align="right" width="75%">الصنف</th>
            </tr>
            ${kitchenItemsHtml}
          </table>
          <div class="center subtitle bold" style="margin-top: 8px;">يرجى تحضير الطعام بأسرع وقت!</div>
        </div>
      </body>
      </html>
    `;
  }

  // Customer / Cashier Clean Spaced 80mm Receipt
  const customerItemsHtml = (order.items || []).map(i => {
    const extList = (i.extras || []).map(e => (typeof e === 'object' ? e.name : e)).filter(Boolean);
    const hasSpicy = (i.extras || []).some(e => e.system_key === 'spicy' || (e.name && e.name.includes('حار'))) || (i.item_name && i.item_name.includes('حار'));
    const spicyBadge = hasSpicy ? ' <span class="spicy">[حار]</span>' : '';
    const extHtml = extList.length ? `<div class="extras">+ إضافات: ${esc(extList.join('، '))}</div>` : '';
    const lineTotal = money(i.quantity * i.unit_price);
    return `
      <tr class="item-row">
        <td align="left" width="30%" class="item-price">${lineTotal}</td>
        <td align="center" width="15%" class="item-qty">${i.quantity}</td>
        <td align="right" width="55%">
          <span class="item-name">${esc(i.item_name)}${i.size_name && i.size_name !== 'عادي' ? ' (' + esc(i.size_name) + ')' : ''}</span>${spicyBadge}
          ${extHtml}
        </td>
      </tr>
    `;
  }).join('');

  const hasExtraTotals = Number(order.delivery_fee || 0) > 0 || Number(order.discount || 0) > 0;
  const showDeliveryDetails = isDelivery && (order.customer_phone || order.area_name || order.detailed_address || (order.customer_name && order.customer_name !== 'عميل المطعم'));

  return `
    <html dir="rtl">
    <head>
      <meta charset="utf-8">
      <style>
        @media print {
          @page { margin: 0; size: 80mm auto; }
          body { margin: 0; padding: 4px 6px; }
        }
        body {
          font-family: 'Cairo', 'Segoe UI', Tahoma, Arial, sans-serif;
          direction: rtl;
          text-align: right;
          margin: 0 auto;
          padding: 6px 8px;
          width: 72mm;
          max-width: 72mm;
          color: #000;
          background: #fff;
          font-weight: bold;
          font-size: 12px;
          line-height: 1.55;
        }
        .receipt-container { width: 100%; margin: 0 auto; }
        .center { text-align: center; }
        .bold { font-weight: bold; }
        .title { font-size: 17px; font-weight: 900; margin: 0 0 2px 0; color: #000; }
        .contact-line { font-size: 11px; margin-bottom: 4px; color: #000; }
        .invoice-title { font-size: 14px; font-weight: 900; margin: 4px 0 1px 0; color: #000; }
        .invoice-date { font-size: 11px; color: #222; margin-bottom: 8px; font-weight: bold; }
        .delivery-box { margin: 6px 0; font-size: 11.5px; line-height: 1.5; }
        .items-table { width: 100%; border-collapse: collapse; margin: 8px 0 6px 0; font-size: 12px; }
        .items-table th { border-bottom: 1.5px solid #000; padding: 4px 0; font-weight: bold; font-size: 12px; color: #000; }
        .items-table td { padding: 5px 0; vertical-align: top; color: #000; }
        .item-qty { font-size: 12.5px; font-weight: 900; color: #000; text-align: center; }
        .item-name { font-weight: bold; }
        .item-price { font-weight: 900; text-align: left; }
        .extras { font-size: 10px; color: #333; padding-right: 6px; margin-top: 2px; }
        .spicy { color: #000; font-weight: bold; }
        .totals-table { width: 100%; border-collapse: collapse; margin: 4px 0; font-size: 11.5px; line-height: 1.5; }
        .totals-table td { padding: 2px 0; }
        .notes-box {
          border: 1px solid #000;
          padding: 4px 6px;
          margin: 6px 0;
          font-size: 11px;
          font-weight: bold;
          background: #fff;
          line-height: 1.4;
        }
        .grand-total {
          font-size: 15px;
          font-weight: 900;
          color: #000;
          border: 2px solid #000;
          padding: 6px;
          margin: 8px 0;
          background: #fff;
          text-align: center;
        }
        .qr-wrap { text-align: center; margin: 8px 0 4px 0; }
        .qr-wrap img { display: inline-block; width: 65px; height: 65px; image-rendering: pixelated; }
        .footer-contact { font-size: 12px; font-weight: bold; text-align: center; margin-top: 6px; color: #000; }
        .dev-credits { font-size: 9px; font-weight: normal; color: #555; text-align: center; margin-top: 2px; direction: ltr; }
      </style>
    </head>
    <body>
      <div class="receipt-container">
        <div class="center">
          <div class="title">بروست — BROOST</div>
          <div class="contact-line">هاتف: 0552802874 · 01092453841</div>
          <div class="invoice-title">فاتورة رقم #${order.id}</div>
          <div class="invoice-date">${esc(order.created_at || '')}</div>
        </div>

        ${showDeliveryDetails ? `
          <div class="delivery-box">
            ${order.customer_name && order.customer_name !== 'عميل المطعم' ? `<div>العميل: ${esc(order.customer_name)}</div>` : ''}
            ${order.customer_phone ? `<div dir="ltr" style="text-align:right">التليفون: ${esc(order.customer_phone)}</div>` : ''}
            ${order.area_name || order.detailed_address ? `<div>العنوان: ${esc(order.area_name || '')} ${esc(order.detailed_address || '')}</div>` : ''}
          </div>
        ` : ''}

        <table class="items-table">
          <thead>
            <tr>
              <th align="left" width="30%">الإجمالي</th>
              <th align="center" width="15%">العدد</th>
              <th align="right" width="55%">الوجبة</th>
            </tr>
          </thead>
          <tbody>
            ${customerItemsHtml}
          </tbody>
        </table>

        ${hasExtraTotals ? `
          <table class="totals-table">
            <tr><td align="left">${money(order.subtotal)}</td><td align="right">الأصناف:</td></tr>
            ${Number(order.delivery_fee || 0) > 0 ? `<tr><td align="left">${money(order.delivery_fee)}</td><td align="right">رسوم التوصيل:</td></tr>` : ''}
            ${Number(order.discount || 0) > 0 ? `<tr><td align="left">-${money(order.discount)}</td><td align="right">الخصم:</td></tr>` : ''}
          </table>
        ` : ''}

        <div class="grand-total">
          الإجمالي الكلي: ${money(order.total)}
        </div>

        ${order.notes ? `<div class="notes-box">ملاحظة: ${esc(order.notes)}</div>` : ''}

        <div class="qr-wrap">
          <img src="${QR_DATA_URL}" alt="QR"/>
        </div>

        <div class="footer-contact">شكراً لزيارتكم — مطعم بروست</div>
        <div class="dev-credits">system by men3em khaled</div>
      </div>
    </body>
    </html>
  `;
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

function daySummaryHtml(summary) {
  const now = new Date();
  const reportDate = now.toLocaleDateString('ar-EG', { year: 'numeric', month: '2-digit', day: '2-digit' });
  const reportTime = now.toLocaleTimeString('ar-EG', { hour: '2-digit', minute: '2-digit' });

  const topItemsHtml = (summary.top_items || []).length ? `
    <div style="border-top:1px dashed #000;margin:8px 0;"></div>
    <div style="font-weight:bold;text-align:right;font-size:12px;margin-bottom:4px">أكثر الأصناف مبيعاً اليوم:</div>
    <table style="width:100%;border-collapse:collapse;text-align:right;font-size:11px">
      <thead>
        <tr style="border-bottom:1px solid #000">
          <th style="padding:4px 2px">الصنف</th>
          <th style="padding:4px 2px;text-align:center">الكمية</th>
          <th style="padding:4px 2px;text-align:left">القيمة</th>
        </tr>
      </thead>
      <tbody>
        ${(summary.top_items || []).map(it => `
          <tr style="border-bottom:1px dotted #ccc">
            <td style="padding:4px 2px">${esc(it.name)}</td>
            <td style="padding:4px 2px;text-align:center"><b>${it.quantity}</b></td>
            <td style="padding:4px 2px;text-align:left">${money(it.sales)}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  ` : '';

  return `<html dir="rtl"><head><meta charset="utf-8"><style>body{font-family:'Cairo',Tahoma,Arial,sans-serif;text-align:center;font-size:12px;color:#000;margin:0;padding:12px}h2{font-size:20px;margin:0 0 4px 0;font-weight:800}h3{font-size:14px;margin:0 0 6px 0;font-weight:700;border-bottom:1px dashed #000;padding-bottom:4px}.meta{font-size:11px;margin:2px 0}.divider{border-top:1px dashed #000;margin:8px 0}.double-divider{border-top:2px solid #000;margin:8px 0}table{width:100%;border-collapse:collapse;margin:4px 0}td{padding:4px 2px;font-size:11px}.highlight-box{border:1px solid #000;padding:6px;margin:8px 0;font-size:13px;font-weight:bold}</style></head><body><h2>بروست — BROOST</h2><h3>تقرير ملخص مبيعات اليوم (X-Report)</h3><p class="meta">التاريخ: ${esc(reportDate)} · الوقت: ${esc(reportTime)}</p><p class="meta">الكاشير: ${esc(summary.cashier_name || 'كاشير بروست')}${summary.shift_id ? ' · وردية #' + summary.shift_id : ''}</p><div class="divider"></div><table><tr><td style="text-align:right">إجمالي الفواتير:</td><td style="text-align:left"><b>${summary.total_orders || 0}</b></td></tr><tr><td style="text-align:right">فواتير مكتملة:</td><td style="text-align:left">${summary.completed_orders_count || 0}</td></tr>${summary.active_orders_count ? `<tr><td style="text-align:right">طلبات جارية:</td><td style="text-align:left">${summary.active_orders_count}</td></tr>` : ''}${summary.cancelled_orders_count ? `<tr><td style="text-align:right">فواتير ملغاة:</td><td style="text-align:left">${summary.cancelled_orders_count}</td></tr>` : ''}</table><div class="divider"></div><table><tr><td style="text-align:right">مبيعات الصالة / سفري (${summary.pickup_count || 0}):</td><td style="text-align:left">${money(summary.pickup_total || 0)}</td></tr><tr><td style="text-align:right">مبيعات الدليفري (${summary.delivery_count || 0}):</td><td style="text-align:left">${money(summary.delivery_total || 0)}</td></tr><tr><td style="text-align:right">منها رسوم التوصيل:</td><td style="text-align:left">${money(summary.delivery_fees || 0)}</td></tr>${summary.discounts > 0 ? `<tr><td style="text-align:right">إجمالي الخصومات:</td><td style="text-align:left">-${money(summary.discounts)}</td></tr>` : ''}</table><div class="highlight-box"><div>إجمالي المبيعات: ${money(summary.total_sales || 0)}</div><div style="font-size:11px;font-weight:normal;margin-top:2px">الصافي بدون توصيل: ${money(summary.net_sales || 0)}</div></div><div class="divider"></div><div style="font-weight:bold;text-align:right;font-size:12px;margin-bottom:4px">تفصيل طرق الدفع:</div><table><tr><td style="text-align:right">نقدي (كاش):</td><td style="text-align:left"><b>${money(summary.cash_total || 0)}</b></td></tr><tr><td style="text-align:right">محافظ إلكترونية / فودافون:</td><td style="text-align:left">${money(summary.wallet_total || 0)}</td></tr><tr><td style="text-align:right">فيزا / بطاقات:</td><td style="text-align:left">${money(summary.visa_total || 0)}</td></tr></table>${summary.expected_cash !== undefined ? `<div class="highlight-box" style="background:#f9f9f9">النقدية بالدرج: ${money(summary.expected_cash)}</div>` : ''}${topItemsHtml}<div class="double-divider"></div><p class="meta" style="margin-top:15px">توقيع المسؤول: ............................</p><p style="font-size:10px;margin-top:8px;color:#444">نظام بروست السحابي لإدارة المطاعم</p></body></html>`;
}

async function printDaySummary() {
  notice('جاري تجهيز تقرير ملخص مبيعات اليوم...');
  const summary = await api('/api/pos/day-summary');
  state.daySummary = summary;
  const html = daySummaryHtml(summary);

  if (window.broostPrinter && typeof window.broostPrinter.printHtml === 'function') {
    window.broostPrinter.printHtml(html);
    notice('تم إرسال ملخص اليوم للطابعة الحرارية بنجاح');
    return;
  }

  if ($('#receipt')) {
    const match = html.match(/<body>([\s\S]*)<\/body>/);
    if (match) $('#receipt').innerHTML = match[1];
  }
  if ($('#receiptDialog') && !$('#receiptDialog').open) $('#receiptDialog').showModal();
  window.print();
  notice('تم فتح نافذة طباعة ملخص مبيعات اليوم');
}

function parsedLocalDate(value) {
  if (!value) return null;
  const raw = String(value).trim();
  const date = new Date(raw.includes('T') ? raw : raw.replace(' ', 'T'));
  return Number.isNaN(date.getTime()) ? null : date;
}

function getElapsedText(createdAt) {
  const d = parsedLocalDate(createdAt);
  if (!d) return 'الآن';
  const diffSec = Math.max(0, Math.floor((new Date() - d) / 1000));
  const diffMin = Math.floor(diffSec / 60);
  const diffHour = Math.floor(diffMin / 60);

  if (diffHour > 0) return `${diffHour} س و ${diffMin % 60} د`;
  if (diffMin > 0) return `${diffMin} دقيقة`;
  return `${diffSec} ثانية`;
}

function getElapsedClass(createdAt) {
  const d = parsedLocalDate(createdAt);
  if (!d) return 'timer-normal';
  const diffMin = Math.floor((new Date() - d) / 60000);
  if (diffMin >= 30) return 'timer-danger';
  if (diffMin >= 15) return 'timer-warning';
  return 'timer-normal';
}

function getOrderDayInfo(createdAt) {
  const d = parsedLocalDate(createdAt);
  if (!d) return { key: 'unknown', label: 'طلبات جارية' };
  const now = new Date();
  const isToday = d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate();
  
  const yesterday = new Date(now);
  yesterday.setDate(yesterday.getDate() - 1);
  const isYesterday = d.getFullYear() === yesterday.getFullYear() && d.getMonth() === yesterday.getMonth() && d.getDate() === yesterday.getDate();

  const daysArabic = ['الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت'];
  const dayName = daysArabic[d.getDay()];
  const formatted = `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}/${d.getFullYear()}`;

  const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  if (isToday) return { key, label: `اليوم — ${dayName} (${formatted})` };
  if (isYesterday) return { key, label: `أمس — ${dayName} (${formatted})` };
  return { key, label: `${dayName} — ${formatted}` };
}

function updateElapsedTimers() {
  document.querySelectorAll?.('.order-card[data-order-card]').forEach(card => {
    const id = card.dataset.orderCard;
    const order = findOrder(id);
    if (!order) return;
    const badge = card.querySelector('.elapsed-badge');
    if (badge) {
      badge.innerHTML = `⏱️ ${getElapsedText(order.created_at)}`;
      badge.className = `elapsed-badge ${getElapsedClass(order.created_at)}`;
    }
  });
}

setInterval(updateElapsedTimers, 10000);

function orderCard(o, inHistory = false) {
  const badgeClass = (o.status || '').toLowerCase();
  const isClosed = o.status === 'COMPLETED' || o.status === 'CANCELLED';
  const canEdit = !isClosed && !inHistory;
  const isDelivery = o.fulfillment === 'DELIVERY';
  const elapsedText = getElapsedText(o.created_at);
  const elapsedClass = getElapsedClass(o.created_at);

  return `
    <article class="order-card status-${badgeClass}" data-order-card="${o.id}">
      <div class="order-card-header">
        <div class="order-header-main">
          <span class="order-card-title">#${o.id} ${esc(o.public_number ? '(' + o.public_number + ')' : '')}</span>
          <span class="order-type-badge ${isDelivery ? 'type-delivery' : 'type-pickup'}">${isDelivery ? 'دليفري' : 'صالة / سفري'}</span>
          <span class="order-card-source">${o.source === 'POS' ? 'كاشير' : 'أونلاين'}</span>
        </div>
        <div class="order-header-meta">
          <span class="elapsed-badge ${elapsedClass}" title="الوقت منذ إنشاء الطلب">⏱️ ${elapsedText}</span>
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
        ${!inHistory && o.status === 'NEW' ? `<button type="button" data-status="PREPARING" data-id="${o.id}">قبول وتجهيز</button>` : ''}
        ${!inHistory && o.status === 'PREPARING' && !isDelivery ? `<button type="button" data-status="READY" data-id="${o.id}">جاهز للاستلام</button>` : ''}
        ${!inHistory && ['PREPARING', 'READY'].includes(o.status) && isDelivery ? `<button type="button" class="btn-dispatch" data-status="DISPATCHED" data-id="${o.id}">خروج للتوصيل</button>` : ''}
        ${!inHistory && ['PREPARING', 'READY', 'DISPATCHED'].includes(o.status) ? `<button type="button" class="btn-complete" data-status="COMPLETED" data-id="${o.id}">${isDelivery ? 'تم التسليم' : 'تم الاستلام'}</button>` : ''}
        ${!inHistory && !isClosed ? `<button type="button" data-status="CANCELLED" data-id="${o.id}" style="color:#dc2626">إلغاء الطلب</button>` : ''}
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
  
  if (!activeList.length) {
    if ($('#activeOrders')) {
      $('#activeOrders').innerHTML = '<p style="grid-column:1/-1;text-align:center;padding:40px;color:var(--text-muted)">لا توجد طلبات جارية قيد التنفيذ حالياً.</p>';
    }
    return;
  }

  // Group active orders by day
  const dayGroups = new Map();
  activeList.forEach(o => {
    const { key, label } = getOrderDayInfo(o.created_at);
    if (!dayGroups.has(key)) {
      dayGroups.set(key, { label, orders: [] });
    }
    dayGroups.get(key).orders.push(o);
  });

  let html = '';
  for (const [_, group] of dayGroups) {
    html += `
      <section class="day-group">
        <div class="day-header">
          <span class="day-title">${esc(group.label)}</span>
          <span class="day-badge">${group.orders.length} ${group.orders.length === 1 ? 'طلب' : 'طلبات'}</span>
        </div>
        <div class="order-grid">
          ${group.orders.map(orderCard).join('')}
        </div>
      </section>
    `;
  }

  if ($('#activeOrders')) $('#activeOrders').innerHTML = html;
}

let history = [];

function renderHistory() {
  const container = $('#history');
  if (!container) return;

  const q = (state.historySearch || '').toLowerCase().trim();
  const filter = state.historyFilter || 'ALL';

  const filtered = history.filter(o => {
    if (filter === 'PICKUP' && o.fulfillment !== 'PICKUP') return false;
    if (filter === 'DELIVERY' && o.fulfillment !== 'DELIVERY') return false;
    if (filter === 'POS' && o.source !== 'POS') return false;
    if (filter === 'ONLINE' && o.source === 'POS') return false;

    if (q) {
      const matchId = String(o.id || '').includes(q);
      const matchPub = String(o.public_number || '').toLowerCase().includes(q);
      const matchName = String(o.customer_name || '').toLowerCase().includes(q);
      const matchPhone = String(o.customer_phone || '').includes(q);
      if (!matchId && !matchPub && !matchName && !matchPhone) return false;
    }
    return true;
  });

  if (!filtered.length) {
    container.innerHTML = `<p style="grid-column:1/-1;text-align:center;padding:40px;color:var(--text-muted)">
      ${q || filter !== 'ALL' ? 'لا توجد فواتير مطابقة لخيارات البحث والفلترة الحالية.' : 'لا توجد فواتير محفوظة في السجل.'}
    </p>`;
    return;
  }

  const dayGroups = new Map();
  filtered.forEach(o => {
    const { key, label } = getOrderDayInfo(o.created_at);
    if (!dayGroups.has(key)) {
      dayGroups.set(key, { label, orders: [] });
    }
    dayGroups.get(key).orders.push(o);
  });

  let html = '';
  for (const [_, group] of dayGroups) {
    const validOrders = group.orders.filter(o => o.status !== 'CANCELLED');
    const daySum = validOrders.reduce((acc, o) => acc + Number(o.total || 0), 0);

    html += `
      <section class="day-group">
        <div class="day-header">
          <span class="day-title">${esc(group.label)}</span>
          <span class="day-badge">${group.orders.length} ${group.orders.length === 1 ? 'فاتورة' : 'فواتير'}</span>
          <span class="day-total">إجمالي: <strong>${money(daySum)}</strong></span>
        </div>
        <div class="order-grid">
          ${group.orders.map(o => orderCard(o, true)).join('')}
        </div>
      </section>
    `;
  }

  container.innerHTML = html;
}

async function loadHistory() {
  history = await api('/api/pos/history?offset=' + state.offset);

  try {
    const summary = await api('/api/pos/day-summary');
    state.daySummary = summary;
    if ($('#historyTodaySales')) $('#historyTodaySales').textContent = money(summary.total_sales || 0);
    if ($('#historyNetHint')) $('#historyNetHint').textContent = `الصافي: ${money(summary.net_sales || 0)}`;
    if ($('#historyTodayCount')) $('#historyTodayCount').textContent = `${summary.total_orders || 0} فاتورة`;
    if ($('#historyBreakdownHint')) $('#historyBreakdownHint').textContent = `${summary.pickup_count || 0} صالة · ${summary.delivery_count || 0} دليفري`;
    if ($('#historyDrawerCash')) $('#historyDrawerCash').textContent = money(summary.expected_cash || summary.cash_total || 0);
    if ($('#historyElectronic')) $('#historyElectronic').textContent = money((summary.wallet_total || 0) + (summary.visa_total || 0));
    if ($('#historyElectronicHint')) $('#historyElectronicHint').textContent = `${money(summary.wallet_total || 0)} محفظة · ${money(summary.visa_total || 0)} فيزا`;
  } catch (_) {}

  renderHistory();

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
    if (order.status === 'COMPLETED') {
      notice('لا يمكن إلغاء طلب مكتمل بالفعل.');
      return;
    }
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
  if (order.status === 'COMPLETED' || order.status === 'CANCELLED') {
    notice('لا يمكن تعديل طلب مكتمل أو ملغي.');
    return;
  }
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
    const item = m.items.find(i => (line.menu_item_sync_id && i.sync_id === line.menu_item_sync_id) || i.name === line.item_name);
    const offer = !item && m.offers.find(o => 'عرض: ' + o.name === line.item_name || o.name === line.item_name);
    const size = item && m.sizes.find(s => s.item_sync_id === item.sync_id && s.name === line.size_name);
    const extras = item ? m.extras.filter(e => e.item_sync_id === item.sync_id && (line.extras || []).some(x => x.name === e.name)) : [];
    
    let unitPrice = Number(line.unit_price || 0);
    if (item) {
      unitPrice = Number(item.base_price) + Number(size?.price_offset || 0) + extras.reduce((a, e) => a + Number(e.price), 0);
    } else if (offer) {
      unitPrice = Number(offer.offer_price);
    }

    return {
      name: item?.name || offer?.name || line.item_name,
      size: size?.name || line.size_name || 'عادي',
      unit_price: unitPrice || Number(line.unit_price || 0),
      item_id: item?.sync_id || line.menu_item_sync_id || null,
      offer_id: offer?.sync_id || null,
      size_id: size?.sync_id || null,
      extra_ids: extras.map(e => e.sync_id),
      spicy: (line.extras || []).some(e => e.system_key === 'spicy'),
      quantity: Number(line.quantity || 1)
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
        <div class="metric-sub">شامل مبيعات الكاش والتوصيل والعهدة</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">إجمالي مبيعات الوردية</div>
        <div class="metric-val">${money(shift.sales)}</div>
        <div class="metric-sub">${shift.invoices || 0} فاتورة مسجلة</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">عهدة بداية الوردية</div>
        <div class="metric-val">${money(shift.opening_cash || 0)}</div>
        <div class="metric-sub">نقدية فتح الدرج</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">حركات الخزينة (مصروف/إيداع)</div>
        <div class="metric-val" style="color:${(shift.movements_total || 0) < 0 ? '#ef4444' : (shift.movements_total || 0) > 0 ? '#16a34a' : 'inherit'}">
          ${(shift.movements_total || 0) > 0 ? '+' : ''}${money(shift.movements_total || 0)}
        </div>
        <div class="metric-sub">صافي المصروفات والإيداعات</div>
      </div>
      ${(Number(shift.wallet || 0) + Number(shift.visa || 0)) > 0 ? `
      <div class="metric-card">
        <div class="metric-label">محافظ وفيزا (غير كاش)</div>
        <div class="metric-val" style="color:#2563eb">${money(Number(shift.wallet || 0) + Number(shift.visa || 0))}</div>
        <div class="metric-sub">${money(shift.wallet || 0)} محفظة · ${money(shift.visa || 0)} فيزا</div>
      </div>` : ''}
    ` : '<div style="grid-column:1/-1;text-align:center;padding:30px;color:var(--text-muted)">لا توجد وردية مفتوحة حالياً. اضغط "فتح وردية" لبدء البيع.</div>';
  }
  if ($('#openShift')) $('#openShift').disabled = !!shift;
  if ($('#closeShift')) $('#closeShift').disabled = !shift;
  if ($('#movement')) $('#movement').disabled = !shift;
}

function formatShiftTime(openedAt, closedAt) {
  const dOpen = parsedLocalDate(openedAt);
  if (!dOpen) return '—';
  const openTime = dOpen.toLocaleTimeString('ar-EG', { hour: '2-digit', minute: '2-digit' });
  const openDate = dOpen.toLocaleDateString('ar-EG', { month: 'short', day: 'numeric' });

  if (!closedAt) {
    return `<div><b>${openDate}</b> · ${openTime}</div><small style="color:#16a34a;font-weight:700">مستمرة حالياً</small>`;
  }

  const dClose = parsedLocalDate(closedAt);
  const closeTime = dClose ? dClose.toLocaleTimeString('ar-EG', { hour: '2-digit', minute: '2-digit' }) : '—';
  return `<div><b>${openDate}</b> · من ${openTime} إلى ${closeTime}</div>`;
}

function formatShiftDiff(actual, expected) {
  if (actual === null || actual === undefined) return '<span style="color:var(--text-muted)">قيد العمل</span>';
  const diff = Math.round((Number(actual) - Number(expected)) * 100) / 100;
  if (diff === 0) {
    return '<span class="shift-diff-tag diff-match">مطابق</span>';
  } else if (diff > 0) {
    return `<span class="shift-diff-tag diff-surplus">+${money(diff)} زيادة</span>`;
  } else {
    return `<span class="shift-diff-tag diff-deficit">${money(diff)} عجز</span>`;
  }
}

async function loadShifts() {
  const rows = await api('/api/pos/shifts');
  if ($('#shifts')) {
    if (!rows || !rows.length) {
      $('#shifts').innerHTML = '<p style="text-align:center;padding:30px;color:var(--text-muted)">لا يوجد سجل للورديات حتى الآن.</p>';
      return;
    }
    $('#shifts').innerHTML = `
      <table class="shifts-table">
        <thead>
          <tr>
            <th>رقم الوردية</th>
            <th>الكاشير</th>
            <th>الوقت والتاريخ</th>
            <th>الفواتير</th>
            <th>المبيعات</th>
            <th>النقد المتوقع</th>
            <th>النقد الفعلي</th>
            <th>فرق العهدة</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map(s => {
            const isOpen = !s.closed_at;
            return `
              <tr class="${isOpen ? 'shift-row-open' : ''}">
                <td>
                  <strong class="shift-num">#${s.id}</strong>
                  <span class="order-badge ${isOpen ? 'new' : 'completed'}">${isOpen ? 'مفتوحة' : 'مغلقة'}</span>
                </td>
                <td><b>${esc(s.cashier_name || 'الكاشير')}</b></td>
                <td>${formatShiftTime(s.opened_at, s.closed_at)}</td>
                <td><b>${s.invoices || 0} فاتورة</b></td>
                <td><b>${money(s.sales)}</b></td>
                <td style="color:#16a34a"><b>${money(s.expected_cash)}</b></td>
                <td>${s.actual_cash === null ? '—' : money(s.actual_cash)}</td>
                <td>${formatShiftDiff(s.actual_cash, s.expected_cash)}</td>
              </tr>
            `;
          }).join('')}
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

if ($('#printDaySummary')) {
  $('#printDaySummary').onclick = () => run(printDaySummary);
}
if ($('#refreshOrders')) {
  $('#refreshOrders').onclick = () => run(loadHistory);
}
if ($('#historySearch')) {
  $('#historySearch').oninput = () => {
    state.historySearch = $('#historySearch').value;
    if ($('#clearHistorySearch')) $('#clearHistorySearch').hidden = !state.historySearch;
    renderHistory();
  };
}
if ($('#clearHistorySearch')) {
  $('#clearHistorySearch').onclick = () => {
    if ($('#historySearch')) $('#historySearch').value = '';
    state.historySearch = '';
    $('#clearHistorySearch').hidden = true;
    renderHistory();
  };
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
if ($('#printKitchen')) $('#printKitchen').onclick = () => printReceipt(true);

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

  // History Filter Pills
  if (b.classList.contains('filter-pill')) {
    const group = b.closest('#historyFilters');
    if (group) {
      group.querySelectorAll('.filter-pill').forEach(pill => pill.classList.remove('active'));
      b.classList.add('active');
      state.historyFilter = b.dataset.filter || 'ALL';
      renderHistory();
    }
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

  // Online Order Alert Actions
  if (b.id === 'alertAcceptBtn' && activeAlertOrder) {
    b.disabled = true;
    try {
      const orderId = activeAlertOrder.id;
      await api('/api/pos/orders/' + orderId, 'PATCH', { status: 'PREPARING' });
      notice(`تم قبول وبدء تجهيز الطلب #${orderId} بنجاح`);
      hideOnlineOrderAlert();
      await refresh();
    } catch (err) {
      notice(err.message);
    } finally {
      b.disabled = false;
    }
    return;
  }

  if (b.id === 'alertViewBtn') {
    hideOnlineOrderAlert();
    const liveBtn = document.querySelector('nav [data-tab="activeTab"]');
    if (liveBtn) liveBtn.click();
    return;
  }

  if (b.id === 'alertDismissBtn') {
    hideOnlineOrderAlert();
    return;
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
