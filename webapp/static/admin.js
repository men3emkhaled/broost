const adminState = {
  key: sessionStorage.getItem("broost_admin_key") || "",
  orders: [],
  dashboardOrders: [],
  businessDay: null,
  ordersLoading: null,
  customers: [],
  areas: [],
  reviews: [],
  menu: { categories: [], items: [], sizes: [], extras: [], offers: [], offer_items: [] },
  settings: null,
  editingArea: null,
  editingCategory: null,
  editingItem: null,
  editingOffer: null,
  offerComponents: [],
  editingReview: null,
  issueOrder: null,
  customerProfile: null,
  proofUrl: null,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const money = (value) => `${Number(value || 0).toLocaleString("ar-EG")} ج`;
const escapeHtml = (text) => String(text ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
const API_BASE_URL = String(window.BROOST_CONFIG?.apiBaseUrl || "").replace(/\/$/, "");
const apiUrl = (url) => /^https?:\/\//i.test(url) ? url : `${API_BASE_URL}${url}`;

async function adminApi(url, options = {}) {
  const response = await fetch(apiUrl(url), {
    headers: { "Content-Type": "application/json", "X-Admin-Key": adminState.key, ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (response.status === 401) {
    sessionStorage.removeItem("broost_admin_key");
    $("#loginOverlay").hidden = false;
  }
  if (!response.ok) throw new Error(data.detail || "تعذر تنفيذ العملية");
  return data;
}

async function login() {
  const password = $("#adminPassword").value;
  $("#loginError").textContent = "";
  try {
    const response = await fetch(apiUrl("/api/admin/login"), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password }) });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "تعذر تسجيل الدخول");
    adminState.key = password;
    sessionStorage.setItem("broost_admin_key", password);
    $("#loginOverlay").hidden = true;
    await loadAll();
  } catch (error) {
    $("#loginError").textContent = error.message;
  }
}

async function loadAll() {
  try {
    await Promise.all([loadOrders(), loadCustomers(), loadAreas(), loadMenu(), loadReviews(), loadSettings()]);
    $("#adminConnection").textContent = "● متصل ومحدث";
    $("#adminConnection").className = "badge badge-success";
  } catch (error) {
    $("#adminConnection").textContent = error.message;
    $("#adminConnection").className = "badge badge-danger";
  }
}

function filterQuery() {
  const params = new URLSearchParams();
  if ($("#ordersFrom").value) params.set("date_from", $("#ordersFrom").value);
  if ($("#ordersTo").value) params.set("date_to", $("#ordersTo").value);
  if ($("#ordersSource").value) params.set("source", $("#ordersSource").value);
  return params.toString();
}

async function loadOrders(force = false) {
  if (adminState.ordersLoading && !force) return adminState.ordersLoading;
  if (adminState.ordersLoading && force) {
    try { await adminState.ordersLoading; } catch { /* retry below */ }
  }
  adminState.ordersLoading = (async () => {
    const query = filterQuery();
    const dashboardRequest = adminApi("/api/admin/orders");
    const filteredRequest = query ? adminApi(`/api/admin/orders?${query}`) : dashboardRequest;
    const businessDayRequest = adminApi("/api/admin/business-day").catch(() => null);
    [adminState.dashboardOrders, adminState.orders, adminState.businessDay] = await Promise.all([
      dashboardRequest,
      filteredRequest,
      businessDayRequest,
    ]);
    renderOrders();
  })();
  try {
    return await adminState.ordersLoading;
  } finally {
    adminState.ordersLoading = null;
  }
}

function parsedLocalDate(value) {
  if (!value) return null;
  const raw = String(value).trim();
  const date = new Date(raw.includes("T") ? raw : raw.replace(" ", "T"));
  return Number.isNaN(date.getTime()) ? null : date;
}

function defaultBusinessDayStart(now = new Date()) {
  const start = new Date(now);
  start.setHours(8, 0, 0, 0);
  if (now < start) start.setDate(start.getDate() - 1);
  return start;
}

function currentBusinessDayStart(now = new Date()) {
  const cashierStart = parsedLocalDate(adminState.businessDay?.business_day_start);
  return cashierStart && cashierStart <= now ? cashierStart : defaultBusinessDayStart(now);
}

function isInBusinessDay(value, start, now = new Date()) {
  const date = parsedLocalDate(value);
  return Boolean(date) && date >= start && date <= now;
}

function productNet(order) {
  return Math.max(0, Number(order.subtotal || 0) - Number(order.discount || 0));
}

function renderDailyOverview() {
  const orders = adminState.dashboardOrders;
  const now = new Date();
  const businessStart = currentBusinessDayStart(now);
  const createdToday = orders.filter((order) => isInBusinessDay(order.created_at, businessStart, now));
  // Cashier reports count a completed/cancelled order in the business period
  // where the order was created, so the website deliberately uses created_at too.
  const completedToday = createdToday.filter((order) => order.status === "COMPLETED");
  const cancelledToday = createdToday.filter((order) => order.status === "CANCELLED");
  const activeOrders = orders.filter((order) => ["NEW", "ACCEPTED", "PREPARING", "READY", "DISPATCHED"].includes(order.status));
  const netSales = completedToday.reduce((sum, order) => sum + productNet(order), 0);
  const deliveryFees = completedToday.reduce((sum, order) => sum + Number(order.delivery_fee || 0), 0);
  const cashSales = completedToday.filter((order) => order.payment_method === "CASH").reduce((sum, order) => sum + productNet(order), 0);
  const walletSales = completedToday.filter((order) => order.payment_method !== "CASH").reduce((sum, order) => sum + productNet(order), 0);
  const onlineCount = createdToday.filter((order) => order.source === "ONLINE").length;
  const posCount = createdToday.filter((order) => order.source === "POS").length;
  const sourceTotal = Math.max(1, onlineCount + posCount);
  const phones = new Set(createdToday.map((order) => String(order.customer_phone_normalized || order.customer_phone || "").replace(/\D/g, "")).filter(Boolean));

  const itemStats = new Map();
  completedToday.forEach((order) => (order.items || []).forEach((item) => {
    const name = String(item.item_name || "صنف").trim();
    const current = itemStats.get(name) || { quantity: 0, sales: 0 };
    const quantity = Number(item.quantity || 0);
    current.quantity += quantity;
    current.sales += Number(item.unit_price || 0) * quantity;
    itemStats.set(name, current);
  }));
  const topItem = [...itemStats.entries()].sort((a, b) => b[1].quantity - a[1].quantity || b[1].sales - a[1].sales)[0];

  const startTime = businessStart.toLocaleTimeString("ar-EG", { hour: "numeric", minute: "2-digit" });
  const periodSource = adminState.businessDay?.business_day_start ? "حسب يوم عمل الكاشير" : "يبدأ افتراضيًا ٨ صباحًا";
  $("#adminTodayLabel").textContent = `من ${startTime} حتى الآن · ${periodSource} · الأرقام تتحدث تلقائيًا`;
  $("#todayNetSales").textContent = money(netSales);
  $("#todayCompleted").textContent = completedToday.length;
  $("#todayAverage").textContent = money(completedToday.length ? netSales / completedToday.length : 0);
  $("#todayActive").textContent = activeOrders.length;
  $("#todayOrdersTotal").textContent = `${createdToday.length} طلب`;
  $("#todayPosCount").textContent = posCount;
  $("#todayOnlineCount").textContent = onlineCount;
  $("#todayPosBar").style.width = `${(posCount / sourceTotal) * 100}%`;
  $("#todayOnlineBar").style.width = `${(onlineCount / sourceTotal) * 100}%`;
  $("#todayPaymentTotal").textContent = money(netSales);
  $("#todayCashSales").textContent = money(cashSales);
  $("#todayWalletSales").textContent = money(walletSales);
  $("#todayDeliveryFees").textContent = money(deliveryFees);
  $("#todayCancelled").textContent = cancelledToday.length;
  $("#todayNewCustomers").textContent = phones.size;
  $("#todayTopItem").textContent = topItem ? topItem[0] : "لا توجد مبيعات مكتملة بعد";
  $("#todayTopItemDetails").textContent = topItem ? `${topItem[1].quantity} قطعة · ${money(topItem[1].sales)}` : "—";
}

function renderOrders() {
  const orders = adminState.orders;
  renderDailyOverview();
  $("#filteredOrdersCount").textContent = `${orders.length} طلب`;

  const groups = {
    new: orders.filter((row) => row.status === "NEW"),
    preparing: orders.filter((row) => ["ACCEPTED", "PREPARING"].includes(row.status)),
    ready: orders.filter((row) => ["READY", "DISPATCHED"].includes(row.status)),
  };
  $("#newCount").textContent = groups.new.length;
  $("#preparingCount").textContent = groups.preparing.length;
  $("#readyCount").textContent = groups.ready.length;
  $("#newOrders").innerHTML = groups.new.map(orderCard).join("") || emptyColumn();
  $("#preparingOrders").innerHTML = groups.preparing.map(orderCard).join("") || emptyColumn();
  $("#readyOrders").innerHTML = groups.ready.map(orderCard).join("") || emptyColumn();

  const closed = orders.filter((row) => ["COMPLETED", "CANCELLED"].includes(row.status));
  $("#closedOrdersTable").innerHTML = closed.map((row) => `
    <tr><td><strong>${escapeHtml(row.public_number)}</strong></td><td>${sourceBadge(row.source)}</td><td><button class="customer-link" data-open-customer="${escapeHtml(row.customer_phone || "")}">${escapeHtml(row.customer_name)}</button>${reliabilityBadge(row.customer_reliability)}</td><td>${paymentLabel(row)}</td><td>${money(row.subtotal)}</td><td>${money(row.delivery_fee)}</td><td>${row.cancelled_by === "TIMEOUT" ? "مرفوض تلقائيًا" : statusLabel(row.status)}</td><td>${formatDate(row.created_at)}</td></tr>`).join("") || `<tr><td colspan="8" class="empty-state">لا توجد طلبات مكتملة أو ملغاة بالفلاتر الحالية.</td></tr>`;
}

function orderCard(order) {
  const reliability = order.customer_reliability || {};
  const proofActions = order.payment_method === "WALLET" && order.payment_status === "PROOF_UPLOADED" ? `
    <button class="btn btn-small" data-show-proof="${order.id}">عرض التحويل</button>
    <button class="btn btn-small btn-primary" data-payment-status="CONFIRMED" data-order-id="${order.id}">تأكيد الدفع</button>
    <button class="btn btn-small btn-danger" data-payment-status="REJECTED" data-order-id="${order.id}">رفض صورة التحويل فقط</button>` : "";
  const redeemedPoints = Number(order.loyalty?.points_redeemed || 0);
  const loyaltyNotice = redeemedPoints
    ? `<div class="notice ${order.status === "CANCELLED" ? "notice-success" : "notice-warning"}">${order.status === "CANCELLED" ? `رجعت ${redeemedPoints} نقطة لرصيد العميل` : `${redeemedPoints} نقطة محجوزة لهذا الطلب وتعود تلقائيًا لو اتلغى`}</div>`
    : "";
  const sourceClass = order.source === "ONLINE" ? "order-source-online" : "order-source-pos";
  return `<article class="card order-card ${sourceClass}">
    <div class="order-card-head"><div><h3>${escapeHtml(order.public_number)}</h3><div class="chips">${sourceBadge(order.source)}<span class="badge">${order.fulfillment === "DELIVERY" ? "دليفري" : "استلام"}</span><span class="badge badge-warning">${statusLabel(order.status)}</span></div></div><strong>${money(order.total)}</strong></div>
    <p><strong>${escapeHtml(order.customer_name)}</strong> · ${escapeHtml(order.customer_phone || "بدون رقم")}</p>
    <div class="customer-trust-row">${reliabilityBadge(reliability)}<span>${reliabilityFacts(reliability)}</span></div>
    ${reliability.needs_call ? `<div class="notice notice-warning trust-warning">اتصل بالعميل للتأكيد قبل تجهيز الطلب.</div>` : ""}
    ${order.fulfillment === "DELIVERY" ? `<p>${escapeHtml(order.area_name)} — ${escapeHtml(order.detailed_address)}</p>` : ""}
    <div class="order-items-mini">${orderItemsSummary(order)}</div>
    ${loyaltyNotice}
    <p>${paymentLabel(order)} · ${formatDate(order.created_at)}</p>
    <div class="inline-actions">${proofActions}${statusActions(order)}${order.customer_phone ? `<button class="btn btn-small" data-open-customer="${escapeHtml(order.customer_phone)}">سجل العميل</button><button class="btn btn-small" data-add-issue="${order.id}" data-customer-label="${escapeHtml(order.customer_name)}">تسجيل ملاحظة</button>` : ""}</div>
  </article>`;
}

function orderItemsSummary(order) {
  return (order.items || []).map((item) => {
    const details = (item.extras || []).map((extra) => extra.name).filter(Boolean).join("، ");
    return `<div><strong>${Number(item.quantity || 1)}× ${escapeHtml(item.item_name)}</strong>${details ? `<small>${escapeHtml(details)}</small>` : ""}</div>`;
  }).join("") || "لا توجد أصناف";
}

function statusActions(order) {
  const cancel = `<button class="btn btn-small btn-danger" data-order-status="CANCELLED" data-order-id="${order.id}">إلغاء الطلب</button>`;
  if (order.payment_method === "WALLET" && order.payment_status !== "CONFIRMED") {
    return `<span class="badge badge-warning">أكد التحويل قبل التجهيز</span>${cancel}`;
  }
  if (order.status === "NEW") return `<button class="btn btn-small btn-primary" data-order-status="PREPARING" data-order-id="${order.id}">تأكيد وبدء التجهيز</button>${cancel}`;
  if (["ACCEPTED", "PREPARING", "READY"].includes(order.status) && order.fulfillment === "DELIVERY") return `<span class="badge badge-brand">جاهز وخرج للدليفري عند تكليف الطيار من السيستم</span>${cancel}`;
  if (["ACCEPTED", "PREPARING"].includes(order.status)) return `<button class="btn btn-small btn-primary" data-order-status="READY" data-order-id="${order.id}">الطلب جاهز</button>${cancel}`;
  if (order.status === "READY") return `<button class="btn btn-small btn-primary" data-order-status="COMPLETED" data-order-id="${order.id}">تم الاستلام</button>${cancel}`;
  if (order.status === "DISPATCHED") return `<button class="btn btn-small btn-primary" data-order-status="COMPLETED" data-order-id="${order.id}">تم التسليم</button>${cancel}`;
  return "";
}

function emptyColumn() { return `<div class="card empty-state">لا توجد طلبات هنا.</div>`; }
function sourceLabel(source) { return source === "ONLINE" ? "أونلاين" : "داخل المطعم"; }
function sourceBadge(source) { return `<span class="badge ${source === "ONLINE" ? "badge-brand" : "badge-success"}">${sourceLabel(source)}</span>`; }
function statusLabel(status) { return ({ NEW: "جديد", ACCEPTED: "مؤكد وجاري التجهيز", PREPARING: "مؤكد وجاري التجهيز", READY: "جاهز", DISPATCHED: "جاهز وخرج للتوصيل", COMPLETED: "تم التسليم", CANCELLED: "ملغي" })[status] || status; }
function paymentLabel(order) {
  if (order.payment_method === "CASH") return "نقدي";
  return ({ AWAITING_PAYMENT: "بانتظار التحويل", PROOF_UPLOADED: "تحويل تحت المراجعة", CONFIRMED: "محفظة مؤكدة", REJECTED: "تحويل مرفوض" })[order.payment_status] || "محفظة";
}
function formatDate(value) { return value ? new Date(value).toLocaleString("ar-EG", { dateStyle: "short", timeStyle: "short" }) : "—"; }
function reliabilityClass(status) { return ({ RELIABLE: "badge-success", REGULAR: "badge-brand", NEEDS_CONFIRMATION: "badge-warning", UNKNOWN: "" })[status] || ""; }
function reliabilityBadge(reliability = {}) { return `<span class="badge trust-badge ${reliabilityClass(reliability.status)}">${escapeHtml(reliability.label || "عميل جديد")}</span>`; }
function reliabilityFacts(reliability = {}) { return `${Number(reliability.completed_orders || 0)} مكتمل · ${Number(reliability.open_issues || 0)} ملاحظة مفتوحة · ${Number(reliability.confirmed_wallets || 0)} محفظة مؤكدة`; }
function issueTypeLabel(type) { return ({ NO_SHOW: "لم يستلم الطلب", WRONG_ADDRESS: "عنوان غير صحيح", UNREACHABLE: "تعذر الوصول إليه", INVALID_WALLET_PROOF: "إثبات محفظة غير صحيح", OTHER: "أخرى" })[type] || type; }

async function patchOrder(id, changes) {
  await adminApi(`/api/admin/orders/${id}`, { method: "PATCH", body: JSON.stringify(changes) });
  await loadOrders(true);
}

async function showProof(id) {
  const response = await fetch(apiUrl(`/api/admin/orders/${id}/proof`), { headers: { "X-Admin-Key": adminState.key } });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    alert(data.detail || "تعذر تحميل إثبات التحويل");
    return;
  }
  if (adminState.proofUrl) URL.revokeObjectURL(adminState.proofUrl);
  adminState.proofUrl = URL.createObjectURL(await response.blob());
  $("#proofImage").src = adminState.proofUrl;
  $("#proofModal").hidden = false;
}

async function loadCustomers() {
  const query = $("#customerSearchInput")?.value.trim() || "";
  adminState.customers = await adminApi(`/api/admin/customers?query=${encodeURIComponent(query)}`);
  $("#customersTable").innerHTML = adminState.customers.map((customer) => `
    <tr>
      <td><strong>${escapeHtml(customer.customer_name)}</strong></td>
      <td dir="ltr">${escapeHtml(customer.customer_phone)}</td>
      <td>${reliabilityBadge(customer)}</td>
      <td>${customer.completed_orders}</td>
      <td>${customer.open_issues}</td>
      <td><strong>${Number(customer.loyalty_points || 0)}</strong> نقطة</td>
      <td>${formatDate(customer.last_order_at)}</td>
      <td><button class="btn btn-small" data-open-customer="${escapeHtml(customer.customer_phone)}">فتح السجل</button></td>
    </tr>`).join("") || `<tr><td colspan="8" class="empty-state">لا يوجد عملاء مطابقون للبحث.</td></tr>`;
}

async function openCustomer(phone) {
  if (!phone) return;
  const profile = await adminApi(`/api/admin/customers/${encodeURIComponent(phone)}`);
  adminState.customerProfile = profile;
  $("#profileCustomerName").textContent = profile.customer_name;
  $("#profileCustomerPhone").textContent = profile.customer_phone;
  const reliability = profile.reliability;
  $("#profileReliability").innerHTML = `
    <div class="profile-trust-card ${reliability.needs_call ? "needs-call" : ""}">
      <div><span class="muted">تقييم السجل</span><h3>${escapeHtml(reliability.label)}</h3></div>
      <div class="trust-stats"><span><strong>${reliability.completed_orders}</strong> طلب مكتمل</span><span><strong>${reliability.open_issues}</strong> ملاحظة مفتوحة</span><span><strong>${reliability.confirmed_wallets}</strong> محفظة مؤكدة</span><span><strong>${Number(profile.loyalty?.points || 0)}</strong> نقطة</span></div>
    </div>`;
  $("#profileIssues").innerHTML = profile.issues.map((issue) => `
    <div class="admin-list-row issue-row ${issue.is_resolved ? "resolved" : ""}">
      <span><strong>${issueTypeLabel(issue.issue_type)}</strong><small class="muted">${escapeHtml(issue.note || "بدون تفاصيل")} · ${formatDate(issue.created_at)}</small></span>
      <span class="inline-actions">${issue.is_resolved ? `<span class="badge badge-success">منتهية</span>` : `<button class="btn btn-small" data-resolve-issue="${issue.id}">إنهاء التنبيه</button>`}<button class="btn btn-small btn-danger" data-delete-issue="${issue.id}">حذف</button></span>
    </div>`).join("") || `<div class="empty-state compact-empty">لا توجد ملاحظات مسجلة على العميل.</div>`;
  $("#profileOrders").innerHTML = profile.orders.map((order) => `
    <tr><td><strong>${escapeHtml(order.public_number)}</strong></td><td>${statusLabel(order.status)}</td><td>${money(order.total)}</td><td>${formatDate(order.created_at)}</td></tr>`).join("");
  $("#customerProfileModal").hidden = false;
}

function openIssue(order) {
  adminState.issueOrder = order;
  $("#issueCustomerLabel").textContent = `${order.customer_name} · ${order.customer_phone} · ${order.public_number}`;
  $("#issueType").value = "NO_SHOW";
  $("#issueNote").value = "";
  $("#issueError").textContent = "";
  $("#customerIssueModal").hidden = false;
}

async function saveIssue() {
  if (!adminState.issueOrder) return;
  try {
    await adminApi(`/api/admin/orders/${adminState.issueOrder.id}/customer-issues`, {
      method: "POST",
      body: JSON.stringify({ issue_type: $("#issueType").value, note: $("#issueNote").value.trim() }),
    });
    $("#customerIssueModal").hidden = true;
    await Promise.all([loadOrders(), loadCustomers()]);
  } catch (error) { $("#issueError").textContent = error.message; }
}

async function loadAreas() {
  adminState.areas = await adminApi("/api/admin/areas");
  $("#areasTable").innerHTML = adminState.areas.map((area) => `
    <tr><td><strong>${escapeHtml(area.name)}</strong></td><td>${money(area.delivery_fee)}</td><td>${area.sort_order}</td><td><span class="badge ${area.is_active ? "badge-success" : "badge-danger"}">${area.is_active ? "ظاهرة" : "مخفية"}</span> <span class="badge ${area.delivery_enabled ? "badge-success" : "badge-warning"}">${area.delivery_enabled ? "التوصيل متاح" : "التوصيل متوقف"}</span></td><td><div class="inline-actions"><button class="btn btn-small" data-edit-area="${area.id}">تعديل</button><button class="btn btn-small ${area.delivery_enabled ? "btn-danger" : "btn-primary"}" data-toggle-area-delivery="${area.id}">${area.delivery_enabled ? "إيقاف التوصيل" : "تشغيل التوصيل"}</button></div></td></tr>`).join("") || `<tr><td colspan="5" class="empty-state">لم تتم إضافة قرى بعد.</td></tr>`;
}

function openArea(area = null) {
  adminState.editingArea = area;
  $("#areaModalTitle").textContent = area ? "تعديل القرية" : "إضافة قرية";
  $("#areaNameInput").value = area?.name || "";
  $("#areaFeeInput").value = area?.delivery_fee ?? "";
  $("#areaSortInput").value = area?.sort_order ?? adminState.areas.length + 1;
  $("#areaActiveInput").checked = area ? Boolean(area.is_active) : true;
  $("#areaDeliveryInput").checked = area ? Boolean(area.delivery_enabled) : true;
  $("#areaError").textContent = "";
  $("#areaModal").hidden = false;
}

async function saveArea() {
  const payload = { name: $("#areaNameInput").value.trim(), delivery_fee: Number($("#areaFeeInput").value), sort_order: Number($("#areaSortInput").value || 0), is_active: $("#areaActiveInput").checked, delivery_enabled: $("#areaDeliveryInput").checked };
  if (!payload.name) return void ($("#areaError").textContent = "اكتب اسم القرية.");
  try {
    await adminApi(adminState.editingArea ? `/api/admin/areas/${adminState.editingArea.id}` : "/api/admin/areas", { method: adminState.editingArea ? "PATCH" : "POST", body: JSON.stringify(payload) });
    $("#areaModal").hidden = true;
    await loadAreas();
  } catch (error) { $("#areaError").textContent = error.message; }
}

async function loadMenu() {
  adminState.menu = await adminApi("/api/admin/menu");
  renderMenu();
}

function activeCategories() { return adminState.menu.categories.filter((row) => !row.is_deleted); }

function renderMenu() {
  const categories = activeCategories();
  $("#adminCategories").innerHTML = categories.map((row) => `
    <div class="admin-list-row"><span><strong>${escapeHtml(row.name)}</strong><small class="muted">ترتيب ${row.sort_order} · ${row.is_active ? "ظاهر" : "مخفي"}</small></span><span class="inline-actions"><button class="btn btn-small" data-edit-category="${row.sync_id}">تعديل</button><button class="btn btn-small btn-danger" data-delete-category="${row.sync_id}">حذف</button></span></div>`).join("") || `<div class="empty-state">لا توجد أقسام.</div>`;
  const filter = $("#menuCategoryFilter");
  const oldValue = filter.value;
  filter.innerHTML = `<option value="">كل الأقسام</option>${categories.map((row) => `<option value="${row.sync_id}">${escapeHtml(row.name)}</option>`).join("")}`;
  if ([...filter.options].some((opt) => opt.value === oldValue)) filter.value = oldValue;
  $("#itemCategoryInput").innerHTML = categories.map((row) => `<option value="${row.sync_id}">${escapeHtml(row.name)}</option>`).join("");
  renderMenuItems();
  renderOffers();
}

function renderMenuItems() {
  const category = $("#menuCategoryFilter").value;
  const items = adminState.menu.items.filter((row) => !row.is_deleted && (!category || row.category_sync_id === category));
  $("#adminMenuItems").innerHTML = items.map((row) => `
    <div class="admin-list-row"><span><strong>${escapeHtml(row.name)}</strong><small class="muted">${money(row.base_price)} · ${row.is_available ? "متاح" : "غير متاح"}</small></span><span class="inline-actions"><button class="btn btn-small" data-edit-item="${row.sync_id}">تعديل</button><button class="btn btn-small btn-danger" data-delete-item="${row.sync_id}">حذف</button></span></div>`).join("") || `<div class="empty-state">لا توجد أصناف في هذا القسم.</div>`;
}

function offerParts(offerId) {
  return (adminState.menu.offer_items || [])
    .filter((row) => row.offer_sync_id === offerId)
    .map((row) => ({ ...row, item: adminState.menu.items.find((item) => item.sync_id === row.item_sync_id) }))
    .filter((row) => row.item && !row.item.is_deleted);
}

function renderOffers() {
  const offers = (adminState.menu.offers || []).filter((row) => !row.is_deleted);
  $("#adminOffers").innerHTML = offers.map((offer) => {
    const parts = offerParts(offer.sync_id);
    const regular = parts.reduce((sum, row) => sum + Number(row.quantity) * Number(row.item.base_price), 0);
    const summary = parts.map((row) => `${Number(row.quantity)}× ${row.item.name}`).join(" + ");
    return `<div class="admin-list-row offer-admin-row"><span><strong>${escapeHtml(offer.name)}</strong><small class="muted">${escapeHtml(summary)}<br><del>${money(regular)}</del> <b class="offer-admin-price">${money(offer.offer_price)}</b> · ${offer.is_active ? "متاح" : "متوقف"}</small></span><span class="inline-actions"><button class="btn btn-small" data-edit-offer="${offer.sync_id}">تعديل</button><button class="btn btn-small btn-danger" data-delete-offer="${offer.sync_id}">حذف</button></span></div>`;
  }).join("") || `<div class="empty-state">لا توجد عروض بعد.</div>`;
}

function openCategory(category = null) {
  adminState.editingCategory = category;
  $("#categoryModalTitle").textContent = category ? "تعديل القسم" : "إضافة قسم";
  $("#categoryNameInput").value = category?.name || "";
  $("#categorySortInput").value = category?.sort_order ?? activeCategories().length + 1;
  $("#categoryActiveInput").checked = category ? Boolean(category.is_active) : true;
  $("#categoryError").textContent = "";
  $("#categoryModal").hidden = false;
}

async function saveCategory() {
  const payload = { name: $("#categoryNameInput").value.trim(), sort_order: Number($("#categorySortInput").value || 0), is_active: $("#categoryActiveInput").checked };
  if (!payload.name) return void ($("#categoryError").textContent = "اكتب اسم القسم.");
  try {
    await adminApi(adminState.editingCategory ? `/api/admin/menu/categories/${adminState.editingCategory.sync_id}` : "/api/admin/menu/categories", { method: adminState.editingCategory ? "PATCH" : "POST", body: JSON.stringify(payload) });
    $("#categoryModal").hidden = true;
    await loadMenu();
  } catch (error) { $("#categoryError").textContent = error.message; }
}

function optionLines(rows, priceKey) { return rows.map((row) => `${row.name} | ${row[priceKey]}`).join("\n"); }
function parseOptionLines(value) {
  return value.split("\n").map((line) => line.trim()).filter(Boolean).map((line) => {
    const [name, rawPrice = "0"] = line.split("|");
    return { name: name.trim(), price: Number(rawPrice.trim() || 0) };
  });
}

function openMenuItem(item = null) {
  adminState.editingItem = item;
  $("#menuItemModalTitle").textContent = item ? "تعديل الصنف" : "إضافة صنف";
  $("#itemNameInput").value = item?.name || "";
  $("#itemCategoryInput").value = item?.category_sync_id || activeCategories()[0]?.sync_id || "";
  $("#itemPriceInput").value = item?.base_price ?? "";
  $("#itemAvailableInput").checked = item ? Boolean(item.is_available) : true;
  $("#itemPopularInput").checked = item ? Boolean(item.is_popular) : false;
  $("#itemSizesInput").value = item ? optionLines(adminState.menu.sizes.filter((row) => row.item_sync_id === item.sync_id), "price_offset") : "";
  $("#itemExtrasInput").value = item ? optionLines(adminState.menu.extras.filter((row) => row.item_sync_id === item.sync_id), "price") : "";
  $("#menuItemError").textContent = "";
  $("#menuItemModal").hidden = false;
}

async function saveMenuItem() {
  const payload = {
    category_sync_id: $("#itemCategoryInput").value,
    name: $("#itemNameInput").value.trim(),
    base_price: Number($("#itemPriceInput").value),
    is_available: $("#itemAvailableInput").checked,
    is_popular: $("#itemPopularInput").checked,
    sizes: parseOptionLines($("#itemSizesInput").value),
    extras: parseOptionLines($("#itemExtrasInput").value),
  };
  if (!payload.name || !payload.category_sync_id) return void ($("#menuItemError").textContent = "اكتب اسم الصنف واختر القسم.");
  try {
    await adminApi(adminState.editingItem ? `/api/admin/menu/items/${adminState.editingItem.sync_id}` : "/api/admin/menu/items", { method: adminState.editingItem ? "PATCH" : "POST", body: JSON.stringify(payload) });
    $("#menuItemModal").hidden = true;
    await loadMenu();
  } catch (error) { $("#menuItemError").textContent = error.message; }
}

function availableOfferItems() {
  return adminState.menu.items.filter((row) => !row.is_deleted);
}

function offerRegularPrice() {
  return adminState.offerComponents.reduce((sum, component) => {
    const item = adminState.menu.items.find((row) => row.sync_id === component.item_sync_id);
    return sum + Number(item?.base_price || 0) * Number(component.quantity || 0);
  }, 0);
}

function renderOfferComponents() {
  const items = availableOfferItems();
  $("#offerComponents").innerHTML = adminState.offerComponents.map((component, index) => `
    <div class="offer-component-row">
      <select class="input" data-offer-item="${index}">${items.map((item) => `<option value="${item.sync_id}" ${item.sync_id === component.item_sync_id ? "selected" : ""}>${escapeHtml(item.name)} — ${money(item.base_price)}</option>`).join("")}</select>
      <input class="input" type="number" min="1" max="30" value="${Number(component.quantity || 1)}" data-offer-quantity="${index}" aria-label="الكمية">
      <button class="btn btn-small btn-danger" type="button" data-remove-offer-component="${index}">حذف</button>
    </div>`).join("");
  $("#offerRegularPrice").textContent = `السعر الأصلي: ${money(offerRegularPrice())}`;
}

function addOfferComponent() {
  const first = availableOfferItems()[0];
  if (!first) return void ($("#offerError").textContent = "أضف صنفًا للمنيو أولًا.");
  adminState.offerComponents.push({ item_sync_id: first.sync_id, quantity: 1 });
  renderOfferComponents();
}

function openOffer(offer = null) {
  adminState.editingOffer = offer;
  $("#offerModalTitle").textContent = offer ? "تعديل العرض" : "إضافة عرض";
  $("#offerNameInput").value = offer?.name || "";
  $("#offerPriceInput").value = offer?.offer_price ?? "";
  $("#offerActiveInput").checked = offer ? Boolean(offer.is_active) : true;
  adminState.offerComponents = offer
    ? offerParts(offer.sync_id).map((row) => ({ item_sync_id: row.item_sync_id, quantity: Number(row.quantity) }))
    : [];
  if (!adminState.offerComponents.length && availableOfferItems().length) addOfferComponent();
  else renderOfferComponents();
  $("#offerError").textContent = "";
  $("#offerModal").hidden = false;
}

async function saveOffer() {
  const payload = {
    name: $("#offerNameInput").value.trim(),
    offer_price: Number($("#offerPriceInput").value),
    is_active: $("#offerActiveInput").checked,
    items: adminState.offerComponents.map((row) => ({
      item_sync_id: row.item_sync_id,
      quantity: Number(row.quantity),
    })),
  };
  if (!payload.name || !payload.items.length) return void ($("#offerError").textContent = "اكتب اسم العرض وأضف مكوّنًا واحدًا على الأقل.");
  if (payload.offer_price >= offerRegularPrice()) return void ($("#offerError").textContent = "سعر العرض لازم يكون أقل من السعر الأصلي.");
  try {
    await adminApi(
      adminState.editingOffer ? `/api/admin/offers/${adminState.editingOffer.sync_id}` : "/api/admin/offers",
      { method: adminState.editingOffer ? "PATCH" : "POST", body: JSON.stringify(payload) },
    );
    $("#offerModal").hidden = true;
    await loadMenu();
  } catch (error) { $("#offerError").textContent = error.message; }
}

async function loadReviews() {
  adminState.reviews = await adminApi("/api/admin/reviews");
  $("#reviewsTable").innerHTML = adminState.reviews.map((review) => `
    <tr><td><strong>${escapeHtml(review.customer_name)}</strong></td><td class="review-text-cell">${escapeHtml(review.review_text)}</td><td>${"★".repeat(review.rating)}</td><td><span class="badge ${review.is_visible ? "badge-success" : ""}">${review.is_visible ? "ظاهر" : "مخفي"}</span></td><td>${review.sort_order}</td><td><div class="inline-actions"><button class="btn btn-small" data-edit-review="${review.id}">تعديل</button><button class="btn btn-small btn-danger" data-delete-review="${review.id}">حذف</button></div></td></tr>`).join("") || `<tr><td colspan="6" class="empty-state">لا توجد آراء بعد، ولذلك القسم مخفي من الموقع.</td></tr>`;
}

function openReview(review = null) {
  adminState.editingReview = review;
  $("#reviewModalTitle").textContent = review ? "تعديل الرأي" : "إضافة رأي حقيقي";
  $("#reviewCustomerName").value = review?.customer_name || "";
  $("#reviewText").value = review?.review_text || "";
  $("#reviewRating").value = String(review?.rating || 5);
  $("#reviewSort").value = review?.sort_order ?? adminState.reviews.length + 1;
  $("#reviewVisible").checked = review ? Boolean(review.is_visible) : true;
  $("#reviewError").textContent = "";
  $("#reviewModal").hidden = false;
}

async function saveReview() {
  const payload = {
    customer_name: $("#reviewCustomerName").value.trim(),
    review_text: $("#reviewText").value.trim(),
    rating: Number($("#reviewRating").value),
    sort_order: Number($("#reviewSort").value || 0),
    is_visible: $("#reviewVisible").checked,
  };
  if (!payload.customer_name || !payload.review_text) return void ($("#reviewError").textContent = "اكتب اسم العميل ونص الرأي الحقيقي.");
  try {
    await adminApi(adminState.editingReview ? `/api/admin/reviews/${adminState.editingReview.id}` : "/api/admin/reviews", { method: adminState.editingReview ? "PATCH" : "POST", body: JSON.stringify(payload) });
    $("#reviewModal").hidden = true;
    await loadReviews();
  } catch (error) { $("#reviewError").textContent = error.message; }
}

async function loadSettings() {
  adminState.settings = await adminApi("/api/admin/settings");
  $("#restaurantName").value = adminState.settings.restaurant_name;
  $("#walletNumberAdmin").value = adminState.settings.wallet_number;
  $("#businessHoursAdmin").value = adminState.settings.business_hours || "";
  $("#branchAddressAdmin").value = adminState.settings.branch_address || "";
  $("#contactPhoneAdmin").value = adminState.settings.contact_phone || "";
  $("#whatsappNumberAdmin").value = adminState.settings.whatsapp_number || "";
  $("#mapUrlAdmin").value = adminState.settings.map_url || "";
  $("#facebookUrlAdmin").value = adminState.settings.facebook_url || "";
  $("#orderingEnabled").checked = adminState.settings.ordering_enabled;
}

async function saveSettings() {
  try {
    await adminApi("/api/admin/settings", { method: "PUT", body: JSON.stringify({
      restaurant_name: $("#restaurantName").value.trim(),
      wallet_number: $("#walletNumberAdmin").value.trim(),
      ordering_enabled: $("#orderingEnabled").checked,
      business_hours: $("#businessHoursAdmin").value.trim(),
      branch_address: $("#branchAddressAdmin").value.trim(),
      contact_phone: $("#contactPhoneAdmin").value.trim(),
      whatsapp_number: $("#whatsappNumberAdmin").value.trim(),
      map_url: $("#mapUrlAdmin").value.trim(),
      facebook_url: $("#facebookUrlAdmin").value.trim(),
    }) });
    $("#settingsMessage").textContent = "تم حفظ الإعدادات.";
    await loadSettings();
  } catch (error) { $("#settingsMessage").textContent = error.message; }
}

$$('[data-admin-view]').forEach((button) => button.addEventListener("click", () => {
  $$('[data-admin-view]').forEach((node) => node.classList.toggle("active", node === button));
  $$('.admin-view').forEach((view) => { view.hidden = view.dataset.view !== button.dataset.adminView; });
}));

$("#loginBtn").addEventListener("click", login);
$("#adminPassword").addEventListener("keydown", (event) => { if (event.key === "Enter") login(); });
$("#logoutBtn").addEventListener("click", () => { sessionStorage.removeItem("broost_admin_key"); location.reload(); });
$("#refreshOrdersBtn").addEventListener("click", () => loadOrders(true));
$("#applyOrderFilters").addEventListener("click", () => loadOrders(true));
$("#customerSearchBtn").addEventListener("click", loadCustomers);
$("#customerSearchInput").addEventListener("keydown", (event) => { if (event.key === "Enter") loadCustomers(); });
$("#addAreaBtn").addEventListener("click", () => openArea());
$("#saveAreaBtn").addEventListener("click", saveArea);
$("#addCategoryBtn").addEventListener("click", () => openCategory());
$("#saveCategoryBtn").addEventListener("click", saveCategory);
$("#addMenuItemBtn").addEventListener("click", () => openMenuItem());
$("#saveMenuItemBtn").addEventListener("click", saveMenuItem);
$("#addOfferBtn").addEventListener("click", () => openOffer());
$("#addOfferComponentBtn").addEventListener("click", addOfferComponent);
$("#saveOfferBtn").addEventListener("click", saveOffer);
$("#addReviewBtn").addEventListener("click", () => openReview());
$("#saveReviewBtn").addEventListener("click", saveReview);
$("#saveIssueBtn").addEventListener("click", saveIssue);
$("#menuCategoryFilter").addEventListener("change", renderMenuItems);
$("#saveSettingsBtn").addEventListener("click", saveSettings);

document.addEventListener("click", async (event) => {
  const close = event.target.closest("[data-close-overlay]");
  if (close) $("#" + close.dataset.closeOverlay).hidden = true;

  const status = event.target.closest("[data-order-status]");
  if (status) {
    if (status.dataset.orderStatus === "CANCELLED" && !confirm("إلغاء الطلب؟ لو استخدم نقاط هترجع لرصيده تلقائيًا.")) return;
    try { await patchOrder(Number(status.dataset.orderId), { status: status.dataset.orderStatus }); }
    catch (error) { alert(error.message); }
  }
  const payment = event.target.closest("[data-payment-status]");
  if (payment) {
    if (payment.dataset.paymentStatus === "REJECTED" && !confirm("ده هيرفض صورة التحويل فقط، والطلب هيفضل مفتوح لحد ما العميل يرفع صورة صحيحة أو تلغي الطلب.")) return;
    try { await patchOrder(Number(payment.dataset.orderId), { payment_status: payment.dataset.paymentStatus }); }
    catch (error) { alert(error.message); }
  }
  const proof = event.target.closest("[data-show-proof]");
  if (proof) await showProof(Number(proof.dataset.showProof));
  const customer = event.target.closest("[data-open-customer]");
  if (customer) await openCustomer(customer.dataset.openCustomer);
  const addIssue = event.target.closest("[data-add-issue]");
  if (addIssue) {
    const order = adminState.orders.find((row) => row.id === Number(addIssue.dataset.addIssue));
    if (order) openIssue(order);
  }
  const resolveIssue = event.target.closest("[data-resolve-issue]");
  if (resolveIssue) {
    await adminApi(`/api/admin/customer-issues/${resolveIssue.dataset.resolveIssue}`, { method: "PATCH", body: JSON.stringify({ is_resolved: true }) });
    await Promise.all([loadOrders(), loadCustomers()]);
    if (adminState.customerProfile) await openCustomer(adminState.customerProfile.customer_phone);
  }
  const deleteIssue = event.target.closest("[data-delete-issue]");
  if (deleteIssue && confirm("حذف هذه الملاحظة نهائيًا؟")) {
    await adminApi(`/api/admin/customer-issues/${deleteIssue.dataset.deleteIssue}`, { method: "DELETE" });
    await Promise.all([loadOrders(), loadCustomers()]);
    if (adminState.customerProfile) await openCustomer(adminState.customerProfile.customer_phone);
  }

  const editArea = event.target.closest("[data-edit-area]");
  if (editArea) openArea(adminState.areas.find((row) => row.id === Number(editArea.dataset.editArea)));
  const toggleArea = event.target.closest("[data-toggle-area-delivery]");
  if (toggleArea) {
    const area = adminState.areas.find((row) => row.id === Number(toggleArea.dataset.toggleAreaDelivery));
    if (area && confirm(area.delivery_enabled ? "إيقاف التوصيل لهذه القرية مؤقتًا؟ ستظل القرية والسعر ظاهرين." : "تشغيل التوصيل لهذه القرية؟")) {
      await adminApi(`/api/admin/areas/${area.id}`, { method: "PATCH", body: JSON.stringify({ delivery_enabled: !area.delivery_enabled }) });
      await loadAreas();
    }
  }

  const editCategory = event.target.closest("[data-edit-category]");
  if (editCategory) openCategory(activeCategories().find((row) => row.sync_id === editCategory.dataset.editCategory));
  const deleteCategory = event.target.closest("[data-delete-category]");
  if (deleteCategory && confirm("حذف القسم وأصنافه من المنيو؟")) { await adminApi(`/api/admin/menu/categories/${deleteCategory.dataset.deleteCategory}`, { method: "DELETE" }); await loadMenu(); }

  const editItem = event.target.closest("[data-edit-item]");
  if (editItem) openMenuItem(adminState.menu.items.find((row) => row.sync_id === editItem.dataset.editItem));
  const deleteItem = event.target.closest("[data-delete-item]");
  if (deleteItem && confirm("حذف الصنف من المنيو؟")) { await adminApi(`/api/admin/menu/items/${deleteItem.dataset.deleteItem}`, { method: "DELETE" }); await loadMenu(); }

  const editOffer = event.target.closest("[data-edit-offer]");
  if (editOffer) openOffer((adminState.menu.offers || []).find((row) => row.sync_id === editOffer.dataset.editOffer));
  const deleteOffer = event.target.closest("[data-delete-offer]");
  if (deleteOffer && confirm("حذف العرض نهائيًا؟")) { await adminApi(`/api/admin/offers/${deleteOffer.dataset.deleteOffer}`, { method: "DELETE" }); await loadMenu(); }
  const removeOfferComponent = event.target.closest("[data-remove-offer-component]");
  if (removeOfferComponent) {
    adminState.offerComponents.splice(Number(removeOfferComponent.dataset.removeOfferComponent), 1);
    renderOfferComponents();
  }

  const editReview = event.target.closest("[data-edit-review]");
  if (editReview) openReview(adminState.reviews.find((row) => row.id === Number(editReview.dataset.editReview)));
  const deleteReview = event.target.closest("[data-delete-review]");
  if (deleteReview && confirm("حذف هذا الرأي من الموقع؟")) { await adminApi(`/api/admin/reviews/${deleteReview.dataset.deleteReview}`, { method: "DELETE" }); await loadReviews(); }
});

$("#offerComponents").addEventListener("change", (event) => {
  if (event.target.matches("[data-offer-item]")) {
    adminState.offerComponents[Number(event.target.dataset.offerItem)].item_sync_id = event.target.value;
  }
  if (event.target.matches("[data-offer-quantity]")) {
    adminState.offerComponents[Number(event.target.dataset.offerQuantity)].quantity = Math.max(1, Number(event.target.value || 1));
  }
  renderOfferComponents();
});

if (adminState.key) {
  $("#loginOverlay").hidden = true;
  loadAll();
} else {
  $("#loginOverlay").hidden = false;
}

setInterval(() => {
  if (adminState.key && !$("[data-view='orders']").hidden) loadOrders().catch(() => {});
}, 5000);
