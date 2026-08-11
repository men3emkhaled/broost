const state = {
  store: null,
  category: "offers",
  cart: JSON.parse(localStorage.getItem("broost_cart") || "[]"),
  fulfillment: localStorage.getItem("broost_fulfillment") || "DELIVERY",
  payment: localStorage.getItem("broost_payment") || "CASH",
  selectedItem: null,
  selectedSize: null,
  selectedExtras: new Set(),
  modalQty: 1,
  order: null,
  loyalty: null,
  accountLoyalty: null,
  loggedPhone: localStorage.getItem("broost_logged_phone") || "",
  rewardCode: "",
  rewardApplied: null,
  orders: [],
  openOrdersAfterLogin: false,
  loyaltyTimer: null,
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const money = (value) => `${Number(value || 0).toLocaleString("ar-EG")} جنيه`;
const API_BASE_URL = String(window.BROOST_CONFIG?.apiBaseUrl || "").replace(/\/$/, "");
const apiUrl = (url) => /^https?:\/\//i.test(url) ? url : `${API_BASE_URL}${url}`;

function cleanCategoryName(name) {
  return String(name || "").replace(/^\s*[0-9٠-٩]+\s*[.\-–—)]*\s*/, "").trim();
}

function stripAreaPrefix(address, areaName) {
  let result = String(address || "").trim();
  const area = String(areaName || "").trim();
  if (!result || !area) return result;
  const escapedArea = area.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const prefix = new RegExp(`^\\s*${escapedArea}(?:\\s*[-–—,:،]\\s*|\\s+|$)`, "i");
  while (result && prefix.test(result)) result = result.replace(prefix, "").trim();
  return result.replace(/^\s*[-–—,:،]+\s*/, "").trim();
}

function selectedAreaName() {
  const option = $("#areaSelect").selectedOptions[0];
  return option && option.value ? option.textContent.trim() : "";
}

function productImage(item) {
  const category = state.store?.menu.categories.find((row) => row.sync_id === item.category_sync_id);
  const label = `${category?.name || ""} ${item.name || ""}`;
  if (/ربع\s+فرخة\s+صدر.*3\s*قطع/i.test(label)) return "/assets/images/meal-quarter-breast-3-v1.webp";
  if (/ربع\s+فرخة\s+ورك.*2\s*قطع/i.test(label)) return "/assets/images/meal-quarter-thigh-2-v1.webp";
  if (/نص\s+فرخة.*5\s*قطع/i.test(label)) return "/assets/images/meal-half-chicken-5-v1.webp";
  if (/فرخة\s+كاملة.*9\s*قطع/i.test(label)) return "/assets/images/meal-whole-chicken-9-v1.webp";
  if (/ستربس|ستريبس/i.test(label)) return "/assets/images/category-strips-v1.webp";
  if (/برجر\s+لحم/i.test(label)) return "/assets/images/category-beef-burger-v1.webp";
  if (/برجر|سندوتش/i.test(label)) return "/assets/images/category-burger-v1.webp";
  if (/ريزو|أرز|ارز/i.test(label)) return "/assets/images/category-rice-v1.webp";
  if (/إضافات|اضافات|بطاطس|صوص|تومية|كول سلو|بيبسي/i.test(label)) return "/assets/images/category-sides-v1.webp";
  return "/assets/images/category-chicken-v1.webp";
}

function safeExternalUrl(value) {
  try {
    const url = new URL(String(value || "").trim());
    return ["http:", "https:"].includes(url.protocol) ? url.href : "";
  } catch { return ""; }
}

function whatsappUrl(value) {
  let digits = String(value || "").replace(/\D/g, "");
  if (digits.startsWith("0")) digits = `20${digits.slice(1)}`;
  return digits ? `https://wa.me/${digits}` : "";
}

function scrollToMenu() {
  showView("menu");
  setTimeout(() => $("#menuSection").scrollIntoView({ behavior: "smooth", block: "start" }), 40);
}

function persistCart() {
  localStorage.setItem("broost_cart", JSON.stringify(state.cart));
}

function itemOptions(itemId) {
  return {
    sizes: state.store.menu.sizes.filter((row) => row.item_sync_id === itemId),
    extras: state.store.menu.extras.filter((row) => row.item_sync_id === itemId),
  };
}

function offerDetails(offerId) {
  const parts = state.store.menu.offer_items
    .filter((row) => row.offer_sync_id === offerId)
    .map((row) => ({
      ...row,
      item: state.store.menu.items.find((item) => item.sync_id === row.item_sync_id),
    }))
    .filter((row) => row.item);
  return {
    parts,
    regularPrice: parts.reduce((sum, row) => sum + Number(row.item.base_price) * Number(row.quantity), 0),
    label: parts.map((row) => `${Number(row.quantity)}× ${row.item.name}`).join(" + "),
  };
}

function currentDeliveryFee() {
  if (state.fulfillment === "PICKUP") return 0;
  const area = state.store?.areas.find((row) => String(row.id) === $("#areaSelect").value);
  return area ? Number(area.delivery_fee) : null;
}

function cartSubtotal() {
  return state.cart.reduce((sum, line) => sum + line.unitPrice * line.quantity, 0);
}

function rewardDiscount() {
  if (!state.rewardApplied || !cartSubtotal()) return 0;
  return Math.min(cartSubtotal(), Number(state.rewardApplied.value || 150));
}

function renderLoyalty() {
  const balanceText = $("#loyaltyBalanceText");
  const hint = $("#loyaltyHint");
  if (!state.loyalty) {
    balanceText.textContent = "اكتب رقم الموبايل لمعرفة رصيدك";
    hint.textContent = "كل 100 نقطة تتحول لكود خصم 150 جنيه على المنتجات.";
    state.rewardApplied = null;
    return;
  }

  balanceText.textContent = `رصيدك ${Number(state.loyalty.points || 0)} نقطة`;
  const codes = state.loyalty.reward_codes || [];
  if (codes.length) {
    hint.textContent = `معاك ${codes.length} كود جاهز. الخصم حتى 150 جنيه ولا يشمل التوصيل.`;
  } else if (!state.loyalty.reward_available) {
    hint.textContent = `فاضلك ${Number(state.loyalty.points_to_reward || 0)} نقطة علشان تنشئ كود 150 جنيه.`;
  } else {
    hint.textContent = "معاك 100 نقطة جاهزة — افتح حسابك وحولها لكود 150 جنيه.";
  }
  renderRewardWallet();
}

function renderRewardWallet() {
  const wallet = $("#rewardWallet");
  if (!wallet) return;
  wallet.hidden = !state.loggedPhone;
  if (!state.loggedPhone) return;
  const profile = state.accountLoyalty || state.loyalty || {};
  const codes = profile.reward_codes || [];
  const button = $("#generateRewardCodeBtn");
  button.disabled = Number(profile.points || 0) < 100;
  button.textContent = button.disabled ? `فاضلك ${Number(profile.points_to_reward || 0)} نقطة` : "إنشاء كود بـ100 نقطة";
  $("#rewardCodesList").innerHTML = codes.length ? codes.map((reward) => `
    <div class="reward-code-card">
      <span><small>كود خصم ${money(reward.value)}</small><strong dir="ltr">${escapeHtml(reward.code)}</strong></span>
      <span class="inline-actions"><button class="btn btn-small" data-copy-reward="${escapeHtml(reward.code)}">نسخ</button><button class="btn btn-small btn-primary" data-use-reward="${escapeHtml(reward.code)}">استخدمه</button></span>
    </div>`).join("") : `<div class="empty-state compact-empty">مفيش أكواد جاهزة حاليًا.</div>`;
}

async function loadLoyalty() {
  const phone = $("#customerPhone").value.trim();
  if (phone.replace(/\D/g, "").length < 7) {
    state.loyalty = null;
    renderLoyalty();
    updateCheckoutTotals();
    return;
  }
  try {
    const profile = await api(`/api/loyalty?phone=${encodeURIComponent(phone)}`);
    if ($("#customerPhone").value.trim() !== phone) return;
    state.loyalty = profile;
  } catch {
    state.loyalty = null;
  }
  renderLoyalty();
  updateCheckoutTotals();
}

function applyCustomerProfile(profile, onlyEmpty = false) {
  const customer = profile?.customer;
  if (!customer) return;
  const fill = (selector, value) => {
    const input = $(selector);
    if (value && (!onlyEmpty || !input.value.trim())) input.value = value;
  };
  fill("#customerName", customer.name);
  fill("#customerPhone", customer.phone || state.loggedPhone);

  const areaSelect = $("#areaSelect");
  if (!onlyEmpty || !areaSelect.value) {
    const matchingOption = [...areaSelect.options].find((option) => (
      customer.area_id && String(option.value) === String(customer.area_id)
    ) || (
      customer.area_name && option.textContent.trim() === customer.area_name.trim()
    ));
    if (matchingOption) areaSelect.value = matchingOption.value;
  }
  const addressInput = $("#customerAddress");
  const cleanProfileAddress = stripAreaPrefix(
    customer.detailed_address,
    selectedAreaName() || customer.area_name
  );
  if (cleanProfileAddress && (!onlyEmpty || !addressInput.value.trim())) {
    addressInput.value = cleanProfileAddress;
  } else {
    addressInput.value = stripAreaPrefix(addressInput.value, selectedAreaName());
  }
  saveCustomerDraft();
}

function renderLoginState() {
  const button = $("#loginBtn");
  if (!state.loggedPhone) {
    button.textContent = "تسجيل الدخول";
    button.classList.remove("is-logged-in");
    $("#ordersBadge").hidden = true;
    return;
  }
  button.textContent = `حسابي · ${Number(state.accountLoyalty?.points || 0)} نقطة`;
  button.classList.add("is-logged-in");
  const badge = $("#ordersBadge");
  badge.textContent = String(state.orders.length);
  badge.hidden = !state.orders.length;
}

function openLoginModal() {
  $("#loginPhone").value = state.loggedPhone || $("#customerPhone").value.trim();
  $("#loginError").textContent = "";
  const preview = $("#loginPointsPreview");
  preview.hidden = !state.loggedPhone;
  preview.textContent = state.loggedPhone
    ? `رصيدك الحالي ${Number(state.accountLoyalty?.points || 0)} نقطة · ${(state.accountLoyalty?.reward_codes || []).length} كود متاح`
    : "";
  renderRewardWallet();
  $("#loginModal").hidden = false;
  setTimeout(() => $("#loginPhone").focus(), 20);
}

async function submitPhoneLogin() {
  const phone = $("#loginPhone").value.trim();
  if (phone.replace(/\D/g, "").length < 7) {
    $("#loginError").textContent = "اكتب رقم موبايل صحيح.";
    return;
  }
  const button = $("#loginSubmitBtn");
  button.disabled = true;
  button.textContent = "جاري الدخول...";
  $("#loginError").textContent = "";
  try {
    const profile = await api(`/api/loyalty?phone=${encodeURIComponent(phone)}`);
    state.loggedPhone = phone;
    state.accountLoyalty = profile;
    state.loyalty = profile;
    localStorage.setItem("broost_logged_phone", phone);
    applyCustomerProfile(profile);
    if (!$("#customerPhone").value.trim()) $("#customerPhone").value = phone;
    saveCustomerDraft();
    renderLoginState();
    renderLoyalty();
    updateCheckoutTotals();
    $("#loginModal").hidden = true;
    await loadCustomerOrders(state.openOrdersAfterLogin);
    state.openOrdersAfterLogin = false;
  } catch (error) {
    $("#loginError").textContent = error.message;
  } finally {
    button.disabled = false;
    button.textContent = "دخول وعرض نقاطي";
  }
}

async function generateRewardCode() {
  if (!state.loggedPhone) return openLoginModal();
  const button = $("#generateRewardCodeBtn");
  button.disabled = true;
  button.textContent = "جاري إنشاء الكود...";
  $("#rewardCodeError").textContent = "";
  try {
    const profile = await api("/api/loyalty/reward-codes", {
      method: "POST",
      body: JSON.stringify({ phone: state.loggedPhone }),
    });
    state.accountLoyalty = profile;
    state.loyalty = profile;
    renderLoginState();
    renderLoyalty();
    const newest = profile.reward_codes?.[0];
    if (newest) $("#rewardCodeError").textContent = `تم إنشاء ${newest.code} — جاهز للاستخدام.`;
  } catch (error) {
    $("#rewardCodeError").textContent = error.message;
  } finally {
    renderRewardWallet();
  }
}

async function applyRewardCode(code = $("#rewardCodeInput").value) {
  const normalized = String(code || "").trim().toUpperCase();
  const status = $("#rewardCodeStatus");
  status.className = "reward-code-status";
  if (!normalized) {
    state.rewardCode = "";
    state.rewardApplied = null;
    status.textContent = "";
    updateCheckoutTotals();
    return;
  }
  if (!state.loyalty) await loadLoyalty();
  const reward = (state.loyalty?.reward_codes || []).find((row) => row.code === normalized);
  if (!reward) {
    state.rewardCode = "";
    state.rewardApplied = null;
    status.textContent = "الكود غير متاح للرقم المكتوب أو تم استخدامه.";
    status.classList.add("is-error");
    updateCheckoutTotals();
    return;
  }
  state.rewardCode = normalized;
  state.rewardApplied = reward;
  $("#rewardCodeInput").value = normalized;
  status.textContent = `تم تطبيق الكود: خصم حتى ${money(reward.value)} على المنتجات.`;
  status.classList.add("is-success");
  updateCheckoutTotals();
}

function renderCartPointsProgress() {
  const subtotal = cartSubtotal();
  const fee = currentDeliveryFee();
  const discount = rewardDiscount();
  const paidTotal = Math.max(0, subtotal - discount + (fee || 0));
  const orderPoints = Math.floor((paidTotal + 0.000001) / 10);
  const title = $("#cartPointsTitle");
  const hint = $("#cartPointsHint");
  let progress = 0;

  if (!state.loyalty) {
    title.textContent = `الأوردر ده هيكسبك ${orderPoints} نقطة`;
    hint.textContent = "سجّل دخولك برقم الموبايل علشان النقاط تتضاف لرصيدك.";
    progress = Math.min(100, orderPoints);
  } else {
    const startingPoints = Math.max(0, Number(state.loyalty.points || 0));
    const afterOrder = startingPoints + orderPoints;
    title.textContent = orderPoints
      ? `الأوردر ده هيضيف لك ${orderPoints} نقطة`
      : state.rewardApplied ? "بتستخدم كود مكافأة في الأوردر ده" : "نقطك مستنياك";
    hint.textContent = afterOrder >= 100
      ? `بعد استلام الطلب هيبقى معاك ${afterOrder} نقطة — تقدر تحول 100 نقطة لكود 150 جنيه.`
      : `بعد استلام الطلب هيبقى معاك ${afterOrder} نقطة، وفاضلك ${100 - afterOrder} نقطة على كود جديد.`;
    progress = Math.min(100, afterOrder);
  }

  $("#pointsProgressBar").style.width = `${progress}%`;
  $("#pointsProgressTrack").setAttribute("aria-valuenow", String(progress));
}

function showView(name) {
  $("#menuView").hidden = name !== "menu";
  $("#checkoutView").hidden = name !== "checkout";
  $("#trackingView").hidden = name !== "tracking";
  $("#cartDock").hidden = name !== "menu" || !state.cart.length;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

async function api(url, options = {}) {
  const response = await fetch(apiUrl(url), {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "تعذر الاتصال بالسيرفر");
  return data;
}

async function loadStore() {
  try {
    const selectedCheckoutArea = $("#areaSelect")?.value || "";
    const selectedLookupArea = $("#deliveryLookupSelect")?.value || "";
    state.store = await api("/api/store");
    $("#brandName").textContent = state.store.restaurant_name || "BROOST";
    $("#footerBrandName").textContent = state.store.restaurant_name || "BROOST";
    $("#storeStatus").textContent = state.store.ordering_enabled ? "● نستقبل طلبات الآن" : "الطلبات متوقفة مؤقتًا";
    $("#storeStatus").className = `badge ${state.store.ordering_enabled ? "badge-success" : "badge-danger"}`;
    $("#storeClosedBanner").hidden = state.store.ordering_enabled;
    $("#walletChoiceBtn").disabled = !state.store.wallet_available;
    if (!state.store.wallet_available && state.payment === "WALLET") state.payment = "CASH";
    renderCategories();
    renderProducts();
    renderAreas();
    if ([...$("#areaSelect").options].some((option) => option.value === selectedCheckoutArea && !option.disabled)) {
      $("#areaSelect").value = selectedCheckoutArea;
    }
    if ([...$("#deliveryLookupSelect").options].some((option) => option.value === selectedLookupArea)) {
      $("#deliveryLookupSelect").value = selectedLookupArea;
    }
    renderStoreInfo();
    renderReviews();
    renderCart();
  } catch (error) {
    $("#storeStatus").textContent = error.message;
    $("#storeStatus").className = "badge badge-danger";
    $("#productGrid").innerHTML = `<div class="empty-state">تعذر تحميل المنيو. حاول مرة أخرى.</div>`;
  }
}

function renderCategories() {
  const categories = state.store.menu.categories.filter((row) => !row.is_deleted && row.is_active);
  $("#categoryBar").innerHTML = [
    `<button class="btn ${state.category === "offers" ? "active" : ""}" data-category="offers">عروض اليوم</button>`,
    ...categories.map((row) => `<button class="btn ${state.category === row.sync_id ? "active" : ""}" data-category="${row.sync_id}">${escapeHtml(cleanCategoryName(row.name))}</button>`),
  ].join("");
}

function renderProducts() {
  if (state.category === "offers") {
    const offers = state.store.menu.offers || [];
    $("#menuCount").textContent = `${offers.length} عرض`;
    $("#productGrid").innerHTML = offers.length ? offers.map((offer) => {
      const details = offerDetails(offer.sync_id);
      const coverItem = details.parts[0]?.item || {};
      return `
        <button class="product-card offer-card" data-offer-id="${offer.sync_id}">
          <span class="offer-ribbon">عرض</span>
          <img class="product-photo" src="${productImage(coverItem)}" alt="" loading="lazy">
          <span class="product-copy">
            <h3>${escapeHtml(offer.name)}</h3>
            <small class="offer-components">${escapeHtml(details.label)}</small>
            <span class="offer-price-row"><del>${money(details.regularPrice)}</del><strong>${money(offer.offer_price)}</strong></span>
          </span>
          <span class="add-mark" aria-hidden="true">+</span>
        </button>`;
    }).join("") : `<div class="empty-state">العروض الجديدة هتنزل هنا.</div>`;
    return;
  }

  const items = state.store.menu.items.filter((item) => item.category_sync_id === state.category);
  $("#menuCount").textContent = `${items.length} صنف`;
  $("#productGrid").innerHTML = items.length ? items.map((item) => `
    <button class="product-card" data-item-id="${item.sync_id}">
      <img class="product-photo" src="${productImage(item)}" alt="" loading="lazy">
      <span class="product-copy"><h3>${escapeHtml(item.name)}</h3><span class="price">${money(item.base_price)}</span></span>
      <span class="add-mark" aria-hidden="true">+</span>
    </button>`).join("") : `<div class="empty-state">${state.category === "offers" ? "عروض اليوم هتنزل هنا قريبًا." : "لا توجد أصناف متاحة في هذا القسم."}</div>`;
}

function addOfferToCart(offerId) {
  const offer = state.store.menu.offers.find((row) => row.sync_id === offerId);
  if (!offer) return;
  const details = offerDetails(offerId);
  if (!details.parts.length) return;
  const signature = `offer|${offerId}`;
  const existing = state.cart.find((line) => line.signature === signature);
  if (existing) existing.quantity += 1;
  else state.cart.push({
    signature,
    offerId,
    itemId: null,
    name: `عرض: ${offer.name}`,
    sizeId: null,
    sizeName: "باكدج",
    extraIds: [],
    extraNames: [details.label],
    spicy: false,
    unitPrice: Number(offer.offer_price),
    quantity: 1,
    isOffer: true,
  });
  persistCart();
  renderCart();
}

function renderAreas() {
  const checkoutOptions = state.store.areas.map((area) => `
    <option value="${area.id}" ${area.delivery_enabled ? "" : "disabled"}>${escapeHtml(area.name)}${area.delivery_enabled ? "" : " — التوصيل متوقف"}</option>`).join("");
  const lookupOptions = state.store.areas.map((area) => `
    <option value="${area.id}">${escapeHtml(area.name)}</option>`).join("");
  $("#areaSelect").innerHTML = `<option value="">اختر القرية</option>${checkoutOptions}`;
  $("#deliveryLookupSelect").innerHTML = `<option value="">اختار القرية</option>${lookupOptions}`;
  if (!state.store.areas.length) {
    $("#deliveryLookupResult").textContent = "لم تتم إضافة قرى للتوصيل بعد.";
    $("#deliveryLookupResult").className = "lookup-result muted";
  }
}

function renderStoreInfo() {
  const store = state.store;
  $("#paymentMethodsInfo").textContent = store.wallet_available ? "نقدي أو محفظة" : "نقدي";
  if (store.business_hours) {
    $("#hoursInfo").hidden = false;
    $("#businessHours").textContent = store.business_hours;
  }
  if (store.branch_address) {
    $("#addressInfo").hidden = false;
    $("#branchAddress").textContent = store.branch_address;
  }

  const links = [];
  const phone = String(store.contact_phone || "").trim();
  if (phone) links.push(`<a class="btn btn-light" href="tel:${escapeHtml(phone.replace(/[^0-9+]/g, ""))}">اتصل بالمطعم</a>`);
  const whatsapp = whatsappUrl(store.whatsapp_number);
  if (whatsapp) links.push(`<a class="btn btn-light" href="${whatsapp}" target="_blank" rel="noopener">واتساب</a>`);
  const map = safeExternalUrl(store.map_url);
  if (map) links.push(`<a class="text-link dark-link" href="${escapeHtml(map)}" target="_blank" rel="noopener">افتح الموقع على الخريطة</a>`);
  const facebook = safeExternalUrl(store.facebook_url);
  if (facebook) links.push(`<a class="text-link dark-link" href="${escapeHtml(facebook)}" target="_blank" rel="noopener">صفحتنا على فيسبوك</a>`);
  $("#storeLinks").innerHTML = links.join("");
  $("#storeInfoHint").textContent = links.length || store.business_hours || store.branch_address
    ? "كل بيانات الفرع في مكان واحد قبل ما تطلب."
    : "بيانات الفرع وطرق التواصل تظهر هنا بمجرد إضافتها من لوحة الأدمن.";
}

function renderReviews() {
  const reviews = state.store.reviews || [];
  $("#reviewsSection").hidden = !reviews.length;
  $("#reviewsGrid").innerHTML = reviews.map((review) => `
    <article class="review-card">
      <div class="review-stars" aria-label="${review.rating} من 5">${"★".repeat(review.rating)}${"☆".repeat(5 - review.rating)}</div>
      <p>“${escapeHtml(review.review_text)}”</p>
      <strong>${escapeHtml(review.customer_name)}</strong>
    </article>`).join("");
}

function openItem(itemId) {
  const item = state.store.menu.items.find((row) => row.sync_id === itemId);
  if (!item) return;
  const options = itemOptions(itemId);
  state.selectedItem = item;
  state.selectedSize = options.sizes[0]?.sync_id || null;
  state.selectedExtras = new Set();
  state.modalQty = 1;
  $("#itemModalTitle").textContent = item.name;
  $("#itemModalImage").src = productImage(item);
  $("#itemModalImage").alt = item.name;
  $("#modalQty").textContent = "1";
  $("#spicyOption").checked = false;
  $("#sizeOptions").innerHTML = options.sizes.length ? `<strong>الحجم</strong>${options.sizes.map((size, index) => `
    <label class="option-row"><span>${escapeHtml(size.name)} ${Number(size.price_offset) ? `(+${money(size.price_offset)})` : ""}</span><input type="radio" name="size" value="${size.sync_id}" ${index === 0 ? "checked" : ""}></label>`).join("")}` : "";
  $("#extraOptions").innerHTML = options.extras.length ? `<strong>الإضافات</strong>${options.extras.map((extra) => `
    <label class="option-row"><span>${escapeHtml(extra.name)} (+${money(extra.price)})</span><input type="checkbox" name="extra" value="${extra.sync_id}"></label>`).join("")}` : "";
  updateModalPrice();
  $("#itemModal").hidden = false;
}

function updateModalPrice() {
  if (!state.selectedItem) return;
  const options = itemOptions(state.selectedItem.sync_id);
  let price = Number(state.selectedItem.base_price);
  const size = options.sizes.find((row) => row.sync_id === state.selectedSize);
  if (size) price += Number(size.price_offset);
  options.extras.filter((row) => state.selectedExtras.has(row.sync_id)).forEach((row) => { price += Number(row.price); });
  $("#addItemBtn").textContent = `إضافة للسلة — ${money(price * state.modalQty)}`;
}

function addSelectedItem() {
  const item = state.selectedItem;
  const options = itemOptions(item.sync_id);
  const size = options.sizes.find((row) => row.sync_id === state.selectedSize) || null;
  const extras = options.extras.filter((row) => state.selectedExtras.has(row.sync_id));
  const spicy = $("#spicyOption").checked;
  const unitPrice = Number(item.base_price) + Number(size?.price_offset || 0) + extras.reduce((sum, row) => sum + Number(row.price), 0);
  const signature = [item.sync_id, size?.sync_id || "", extras.map((row) => row.sync_id).sort().join(","), spicy].join("|");
  const existing = state.cart.find((line) => line.signature === signature);
  if (existing) existing.quantity += state.modalQty;
  else state.cart.push({
    signature,
    itemId: item.sync_id,
    name: item.name,
    sizeId: size?.sync_id || null,
    sizeName: size?.name || "عادي",
    extraIds: extras.map((row) => row.sync_id),
    extraNames: extras.map((row) => row.name),
    spicy,
    unitPrice,
    quantity: state.modalQty,
  });
  persistCart();
  renderCart();
  $("#itemModal").hidden = true;
}

function renderCart() {
  const count = state.cart.reduce((sum, line) => sum + line.quantity, 0);
  $("#cartDock").hidden = !count || $("#menuView").hidden;
  $("#cartDockCount").textContent = `${count} صنف`;
  $("#cartDockTotal").textContent = `${money(cartSubtotal())} + رسوم التوصيل`;
  $("#checkoutCart").innerHTML = state.cart.map((line, index) => `
    <div class="cart-row">
      <span><strong>${escapeHtml(line.name)}</strong><small class="muted">${escapeHtml([line.sizeName, ...(line.extraNames || []), line.spicy ? "حار" : ""].filter(Boolean).join(" · "))}</small></span>
      <span class="qty"><button data-cart-minus="${index}">−</button><b>${line.quantity}</b><button data-cart-plus="${index}">+</button></span>
    </div>`).join("") || `<div class="empty-state">السلة فاضية.</div>`;
  updateCheckoutTotals();
}

function updateCheckoutTotals() {
  if (!state.store) return;
  const subtotal = cartSubtotal();
  const fee = currentDeliveryFee();
  renderLoyalty();
  const discount = rewardDiscount();
  $("#checkoutSubtotal").textContent = money(subtotal);
  $("#checkoutDiscountRow").hidden = !discount;
  $("#checkoutDiscount").textContent = `− ${money(discount)}`;
  $("#checkoutDelivery").textContent = fee === null ? "اختر القرية" : fee ? money(fee) : "لا يوجد";
  $("#checkoutTotal").textContent = money(subtotal - discount + (fee || 0));
  const submit = $("#submitOrderBtn");
  const canOrder = Boolean(state.store.ordering_enabled);
  submit.disabled = !canOrder;
  submit.textContent = canOrder ? "تأكيد الطلب" : "المطعم مقفول حاليًا";
  renderCartPointsProgress();
  localStorage.setItem("broost_fulfillment", state.fulfillment);
  localStorage.setItem("broost_payment", state.payment);
}

function setChoice(selector, button, stateKey, value) {
  $$(selector).forEach((node) => node.classList.toggle("active", node === button));
  state[stateKey] = value;
}

function openCheckout() {
  if (!state.cart.length) return;
  $$("[data-fulfillment]").forEach((btn) => btn.classList.toggle("active", btn.dataset.fulfillment === state.fulfillment));
  $$("[data-payment]").forEach((btn) => btn.classList.toggle("active", btn.dataset.payment === state.payment));
  $$(".delivery-only").forEach((node) => { node.hidden = state.fulfillment !== "DELIVERY"; });
  renderCart();
  showView("checkout");
}

async function submitOrder() {
  $("#checkoutError").textContent = "";
  if (!state.store?.ordering_enabled) {
    $("#checkoutError").textContent = "المطعم مقفول حاليًا. المنيو محفوظة عندك وتقدر تطلب أول ما الكاشير يفتح.";
    return;
  }
  const name = $("#customerName").value.trim();
  const phone = $("#customerPhone").value.trim();
  const areaId = $("#areaSelect").value;
  const address = stripAreaPrefix($("#customerAddress").value, selectedAreaName());
  $("#customerAddress").value = address;
  if (!name || !phone) return void ($("#checkoutError").textContent = "اكتب الاسم ورقم الموبايل.");
  if (state.fulfillment === "DELIVERY" && (!areaId || !address)) return void ($("#checkoutError").textContent = "اختيار القرية وكتابة العنوان بالتفصيل إجباريان للدليفري.");
  const selectedArea = state.store.areas.find((area) => String(area.id) === String(areaId));
  if (state.fulfillment === "DELIVERY" && !selectedArea?.delivery_enabled) return void ($("#checkoutError").textContent = "التوصيل للقرية المختارة متوقف حاليًا.");
  if (!state.cart.length) return void ($("#checkoutError").textContent = "السلة فاضية.");

  const button = $("#submitOrderBtn");
  button.disabled = true;
  button.textContent = "جاري حفظ الطلب...";
  let requestId = localStorage.getItem("broost_client_request_id");
  if (!requestId) {
    requestId = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
    localStorage.setItem("broost_client_request_id", requestId);
  }
  try {
    const order = await api("/api/orders", {
      method: "POST",
      body: JSON.stringify({
        client_request_id: requestId,
        fulfillment: state.fulfillment,
        payment_method: state.payment,
        customer_name: name,
        customer_phone: phone,
        area_id: state.fulfillment === "DELIVERY" ? Number(areaId) : null,
        detailed_address: state.fulfillment === "DELIVERY" ? address : "",
        notes: $("#orderNotes").value.trim(),
        redeem_reward: false,
        reward_code: state.rewardApplied?.code || "",
        items: state.cart.map((line) => ({
          item_id: line.offerId ? null : line.itemId,
          offer_id: line.offerId || null,
          quantity: line.quantity,
          size_id: line.offerId ? null : line.sizeId,
          extra_ids: line.offerId ? [] : (line.extraIds || []),
          spicy: line.offerId ? false : Boolean(line.spicy),
        })),
      }),
    });
    localStorage.setItem("broost_active_order", order.resume_token);
    history.replaceState(null, "", `/?order=${encodeURIComponent(order.resume_token)}`);
    localStorage.removeItem("broost_client_request_id");
    state.order = order;
    state.loyalty = order.loyalty || state.loyalty;
    state.rewardCode = "";
    state.rewardApplied = null;
    $("#rewardCodeInput").value = "";
    $("#rewardCodeStatus").textContent = "";
    state.cart = [];
    persistCart();
    renderOrder();
    showView("tracking");
    $("#resumeOrderBtn").hidden = false;
    loadCustomerOrders(false);
  } catch (error) {
    $("#checkoutError").textContent = error.message;
  } finally {
    button.disabled = !state.store?.ordering_enabled;
    button.textContent = state.store?.ordering_enabled ? "تأكيد الطلب" : "المطعم مقفول حاليًا";
  }
}

function renderOrder() {
  const order = state.order;
  if (!order) return;
  const status = order.status === "ACCEPTED" ? "PREPARING" : order.status;
  $("#trackNumber").textContent = order.public_number;
  $("#trackPayment").textContent = paymentLabel(order.payment_method, order.payment_status);
  const titles = {
    NEW: "تم استلام طلبك",
    PREPARING: "تم تأكيد طلبك وجاري التجهيز",
    READY: order.fulfillment === "PICKUP" ? "طلبك جاهز للاستلام" : "طلبك جاهز وخرج للدليفري",
    DISPATCHED: "طلبك جاهز وخرج للدليفري",
    COMPLETED: "تم تسليم الطلب",
    CANCELLED: "تم إلغاء الطلب",
  };
  $("#trackTitle").textContent = titles[status] || "متابعة الطلب";
  $("#trackDescription").textContent = order.fulfillment === "DELIVERY"
    ? `${order.area_name} — ${stripAreaPrefix(order.detailed_address, order.area_name)}`
    : "استلام من المطعم";
  const isDelivery = order.fulfillment === "DELIVERY";
  const timelineStatus = isDelivery && status === "READY" ? "DISPATCHED" : status;
  const steps = isDelivery
    ? ["NEW", "PREPARING", "DISPATCHED", "COMPLETED"]
    : ["NEW", "PREPARING", "READY", "COMPLETED"];
  const currentIndex = Math.max(0, steps.indexOf(timelineStatus));
  const labels = {
    NEW: "تم إرسال الطلب",
    PREPARING: "مؤكد وجاري التجهيز",
    READY: "جاهز للاستلام",
    DISPATCHED: "جاهز وخرج للدليفري",
    COMPLETED: "تم التسليم",
  };
  $("#orderTimeline").innerHTML = steps.map((step, index) => `
    <div class="timeline-step ${index <= currentIndex && status !== "CANCELLED" ? "active" : ""} ${index === currentIndex && status !== "CANCELLED" ? "current" : ""}"><span class="timeline-dot">${index < currentIndex ? "✓" : index + 1}</span><strong>${labels[step]}</strong></div>`).join("");
  if (status === "CANCELLED") {
    const message = order.cancelled_by === "CUSTOMER"
      ? "تم إلغاء الطلب بناءً على طلبك."
      : "تم إلغاء الطلب من المطعم.";
    $("#orderTimeline").innerHTML = `<div class="notice notice-danger">${message}</div>`;
  }

  const loyalty = order.loyalty || {};
  if (
    state.loggedPhone
    && String(state.loggedPhone).replace(/\D/g, "") === String(order.customer_phone || "").replace(/\D/g, "")
  ) {
    state.accountLoyalty = loyalty;
    renderLoginState();
  }
  const loyaltyMessages = [];
  if (order.reward?.code && status === "CANCELLED") loyaltyMessages.push(`كود ${order.reward.code} رجع متاح في حسابك.`);
  else if (order.reward?.code) loyaltyMessages.push(`استخدمت كود ${order.reward.code} وخصمت ${money(order.discount)} من المنتجات.`);
  if (Number(loyalty.points_redeemed || 0) && status !== "CANCELLED") loyaltyMessages.push(`استخدمت ${Number(loyalty.points_redeemed)} نقطة في مكافأة الأوردر.`);
  if (status === "COMPLETED" && Number(loyalty.points_earned || 0)) loyaltyMessages.push(`اتضاف لك ${Number(loyalty.points_earned)} نقطة.`);
  else if (!["COMPLETED", "CANCELLED"].includes(status) && Number(loyalty.pending_points || 0)) loyaltyMessages.push(`بعد استلام الطلب هتكسب ${Number(loyalty.pending_points)} نقطة.`);
  if (status === "CANCELLED" && Number(loyalty.points_redeemed || 0)) loyaltyMessages.push(`${Number(loyalty.points_redeemed)} نقطة رجعت كاملة لرصيدك.`);
  loyaltyMessages.push(`رصيدك الحالي ${Number(loyalty.points || 0)} نقطة.`);
  $("#trackLoyalty").innerHTML = `<strong>نقط بروست</strong><span>${loyaltyMessages.join(" ")}</span>`;

  $("#trackingItems").innerHTML = order.items.map((line) => `
    <div class="cart-row"><span>${line.quantity} × ${escapeHtml(line.item_name)}</span><strong>${money(line.unit_price * line.quantity)}</strong></div>`).join("");
  $("#trackSubtotal").textContent = money(order.subtotal);
  $("#trackDiscountRow").hidden = !Number(order.discount || 0);
  $("#trackDiscount").textContent = `− ${money(order.discount)}`;
  $("#trackDelivery").textContent = order.delivery_fee ? money(order.delivery_fee) : "لا يوجد";
  $("#trackTotal").textContent = money(order.total);
  const canCancel = ["NEW", "PREPARING", "READY"].includes(status);
  $("#cancelOrderBtn").hidden = !canCancel;
  $("#cancelOrderError").textContent = "";
  const needsProof = order.payment_method === "WALLET" && ["AWAITING_PAYMENT", "REJECTED"].includes(order.payment_status);
  $("#walletPanel").hidden = !needsProof;
  if (needsProof) {
    $("#walletNumber").textContent = order.wallet_number || "";
    $("#walletAmount").textContent = money(order.total);
    $("#proofError").textContent = order.payment_status === "REJECTED" ? "إثبات التحويل السابق مرفوض. ارفع صورة صحيحة." : "";
  }
}

async function cancelOrder() {
  if (!state.order) return;
  if (!window.confirm("متأكد إنك عاوز تلغي الطلب؟")) return;
  const button = $("#cancelOrderBtn");
  button.disabled = true;
  button.textContent = "جاري إلغاء الطلب...";
  $("#cancelOrderError").textContent = "";
  try {
    state.order = await api(`/api/orders/${encodeURIComponent(state.order.resume_token)}/cancel`, {
      method: "POST",
    });
    state.loyalty = state.order.loyalty || state.loyalty;
    state.accountLoyalty = state.loyalty;
    renderOrder();
    loadCustomerOrders(false);
  } catch (error) {
    $("#cancelOrderError").textContent = error.message;
  } finally {
    button.disabled = false;
    button.textContent = "إلغاء الطلب";
  }
}

async function resumeOrder() {
  const token = new URLSearchParams(location.search).get("order") || localStorage.getItem("broost_active_order");
  if (!token) return;
  try {
    state.order = await api(`/api/orders/${encodeURIComponent(token)}`);
    renderOrder();
    showView("tracking");
    $("#resumeOrderBtn").hidden = false;
  } catch {
    localStorage.removeItem("broost_active_order");
    $("#resumeOrderBtn").hidden = true;
  }
}

function customerOrderStatus(order) {
  const status = order.status === "ACCEPTED" ? "PREPARING" : order.status;
  return {
    NEW: "تم إرسال الطلب",
    PREPARING: "جاري التجهيز",
    READY: "جاهز للاستلام",
    DISPATCHED: "خرج للتوصيل",
    COMPLETED: "تم التسليم",
    CANCELLED: "ملغي",
  }[status] || status;
}

function renderCustomerOrders() {
  const list = $("#customerOrdersList");
  list.innerHTML = state.orders.length ? state.orders.map((order) => `
    <button class="customer-order-card" data-open-order="${escapeHtml(order.resume_token)}">
      <span class="customer-order-main"><strong>${escapeHtml(order.public_number)}</strong><small>${new Date(order.created_at).toLocaleString("ar-EG", { dateStyle: "medium", timeStyle: "short" })}</small></span>
      <span class="customer-order-meta"><span class="badge ${order.status === "CANCELLED" ? "badge-danger" : order.status === "COMPLETED" ? "badge-success" : "badge-brand"}">${customerOrderStatus(order)}</span><strong>${money(order.total)}</strong></span>
    </button>`).join("") : `<div class="empty-state">لسه مفيش طلبات مسجلة بالرقم ده.</div>`;
}

async function loadCustomerOrders(openModal = false) {
  if (!state.loggedPhone) {
    state.openOrdersAfterLogin = true;
    openLoginModal();
    return;
  }
  $("#ordersError").textContent = "";
  try {
    const result = await api(`/api/customer/orders?phone=${encodeURIComponent(state.loggedPhone)}`);
    state.orders = result.orders || [];
    state.accountLoyalty = result.loyalty || state.accountLoyalty;
    if (state.accountLoyalty) state.loyalty = state.accountLoyalty;
    renderLoginState();
    renderCustomerOrders();
    if (openModal) $("#ordersModal").hidden = false;
  } catch (error) {
    $("#ordersError").textContent = error.message;
    if (openModal) $("#ordersModal").hidden = false;
  }
}

async function openOrderFromHistory(token) {
  try {
    state.order = await api(`/api/orders/${encodeURIComponent(token)}`);
    localStorage.setItem("broost_active_order", token);
    history.replaceState(null, "", `/?order=${encodeURIComponent(token)}`);
    $("#ordersModal").hidden = true;
    $("#resumeOrderBtn").hidden = false;
    renderOrder();
    showView("tracking");
  } catch (error) {
    $("#ordersError").textContent = error.message;
  }
}

async function uploadProof() {
  const file = $("#proofFile").files[0];
  if (!file) return void ($("#proofError").textContent = "اختر سكرين شوت التحويل.");
  if (file.size > 6 * 1024 * 1024) return void ($("#proofError").textContent = "حجم الصورة أكبر من 6 ميجابايت.");
  const button = $("#uploadProofBtn");
  button.disabled = true;
  button.textContent = "جاري الرفع...";
  try {
    const dataBase64 = await fileToBase64(file);
    state.order = await api(`/api/orders/${encodeURIComponent(state.order.resume_token)}/proof`, {
      method: "POST",
      body: JSON.stringify({ filename: file.name, mime_type: file.type, data_base64: dataBase64, transfer_phone_suffix: $("#transferSuffix").value.trim() }),
    });
    renderOrder();
  } catch (error) {
    $("#proofError").textContent = error.message;
  } finally {
    button.disabled = false;
    button.textContent = "رفع إثبات التحويل";
  }
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1]);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function paymentLabel(method, status) {
  if (method === "CASH") return "نقدي عند الاستلام";
  return { AWAITING_PAYMENT: "بانتظار التحويل", PROOF_UPLOADED: "التحويل تحت المراجعة", CONFIRMED: "التحويل مؤكد", REJECTED: "التحويل مرفوض" }[status] || "محفظة";
}

function escapeHtml(text) {
  return String(text ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
}

function saveCustomerDraft() {
  const cleanAddress = stripAreaPrefix($("#customerAddress").value, selectedAreaName());
  if ($("#customerAddress").value !== cleanAddress) $("#customerAddress").value = cleanAddress;
  localStorage.setItem("broost_customer_draft", JSON.stringify({
    name: $("#customerName").value,
    phone: $("#customerPhone").value,
    area: $("#areaSelect").value,
    address: cleanAddress,
    notes: $("#orderNotes").value,
  }));
}

function restoreCustomerDraft() {
  try {
    const draft = JSON.parse(localStorage.getItem("broost_customer_draft") || "{}");
    $("#customerName").value = draft.name || "";
    $("#customerPhone").value = draft.phone || "";
    $("#areaSelect").value = draft.area || "";
    $("#customerAddress").value = stripAreaPrefix(draft.address, selectedAreaName());
    $("#orderNotes").value = draft.notes || "";
  } catch { /* ignore an invalid local draft */ }
}

$("#categoryBar").addEventListener("click", (event) => {
  const button = event.target.closest("[data-category]");
  if (!button) return;
  state.category = button.dataset.category;
  renderCategories();
  renderProducts();
});

$("#productGrid").addEventListener("click", (event) => {
  const offerButton = event.target.closest("[data-offer-id]");
  if (offerButton) return addOfferToCart(offerButton.dataset.offerId);
  const button = event.target.closest("[data-item-id]");
  if (button) openItem(button.dataset.itemId);
});

$("#sizeOptions").addEventListener("change", (event) => { state.selectedSize = event.target.value; updateModalPrice(); });
$("#extraOptions").addEventListener("change", (event) => { event.target.checked ? state.selectedExtras.add(event.target.value) : state.selectedExtras.delete(event.target.value); updateModalPrice(); });
$("#spicyOption").addEventListener("change", updateModalPrice);
$("#modalMinus").addEventListener("click", () => { state.modalQty = Math.max(1, state.modalQty - 1); $("#modalQty").textContent = state.modalQty; updateModalPrice(); });
$("#modalPlus").addEventListener("click", () => { state.modalQty = Math.min(30, state.modalQty + 1); $("#modalQty").textContent = state.modalQty; updateModalPrice(); });
$("#addItemBtn").addEventListener("click", addSelectedItem);
$("#closeItemModal").addEventListener("click", () => { $("#itemModal").hidden = true; });

$("#checkoutCart").addEventListener("click", (event) => {
  const plus = event.target.closest("[data-cart-plus]");
  const minus = event.target.closest("[data-cart-minus]");
  if (plus) state.cart[Number(plus.dataset.cartPlus)].quantity += 1;
  if (minus) {
    const index = Number(minus.dataset.cartMinus);
    state.cart[index].quantity -= 1;
    if (state.cart[index].quantity <= 0) state.cart.splice(index, 1);
  }
  if (plus || minus) { persistCart(); renderCart(); }
});

$$('[data-fulfillment]').forEach((button) => button.addEventListener("click", () => {
  setChoice('[data-fulfillment]', button, "fulfillment", button.dataset.fulfillment);
  $$(".delivery-only").forEach((node) => { node.hidden = state.fulfillment !== "DELIVERY"; });
  updateCheckoutTotals();
}));
$$('[data-payment]').forEach((button) => button.addEventListener("click", () => {
  if (button.disabled) return;
  setChoice('[data-payment]', button, "payment", button.dataset.payment);
  updateCheckoutTotals();
}));

$("#areaSelect").addEventListener("change", () => {
  $("#customerAddress").value = stripAreaPrefix(
    $("#customerAddress").value,
    selectedAreaName()
  );
  updateCheckoutTotals();
});
$("#customerPhone").addEventListener("input", () => {
  clearTimeout(state.loyaltyTimer);
  state.loyaltyTimer = setTimeout(loadLoyalty, 350);
});
$("#deliveryLookupSelect").addEventListener("change", (event) => {
  const area = state.store?.areas.find((row) => String(row.id) === event.target.value);
  const result = $("#deliveryLookupResult");
  if (!area) {
    result.textContent = "اختار قريتك لمعرفة الرسوم";
    result.className = "lookup-result";
    return;
  }
  result.innerHTML = area.delivery_enabled
    ? `التوصيل إلى <strong>${escapeHtml(area.name)}</strong> بـ <strong>${money(area.delivery_fee)}</strong>`
    : `التوصيل إلى <strong>${escapeHtml(area.name)}</strong> متوقف مؤقتًا · الرسوم المعتادة <strong>${money(area.delivery_fee)}</strong>`;
  result.className = `lookup-result has-value ${area.delivery_enabled ? "" : "is-paused"}`;
});
$("#headerOrderBtn").addEventListener("click", scrollToMenu);
$("#heroOrderBtn").addEventListener("click", scrollToMenu);
$("#loginBtn").addEventListener("click", openLoginModal);
$("#ordersBtn").addEventListener("click", () => loadCustomerOrders(true));
$("#closeOrdersModal").addEventListener("click", () => { $("#ordersModal").hidden = true; });
$("#customerOrdersList").addEventListener("click", (event) => {
  const button = event.target.closest("[data-open-order]");
  if (button) openOrderFromHistory(button.dataset.openOrder);
});
$("#closeLoginModal").addEventListener("click", () => { $("#loginModal").hidden = true; });
$("#loginSubmitBtn").addEventListener("click", submitPhoneLogin);
$("#generateRewardCodeBtn").addEventListener("click", generateRewardCode);
$("#rewardCodesList").addEventListener("click", async (event) => {
  const copy = event.target.closest("[data-copy-reward]");
  const use = event.target.closest("[data-use-reward]");
  if (copy) {
    await navigator.clipboard.writeText(copy.dataset.copyReward);
    copy.textContent = "تم النسخ";
  }
  if (use) {
    $("#loginModal").hidden = true;
    $("#rewardCodeInput").value = use.dataset.useReward;
    await applyRewardCode(use.dataset.useReward);
    if (state.cart.length) openCheckout();
  }
});
$("#applyRewardCodeBtn").addEventListener("click", () => applyRewardCode());
$("#rewardCodeInput").addEventListener("input", (event) => {
  event.target.value = event.target.value.toUpperCase();
  if (state.rewardApplied?.code !== event.target.value.trim()) {
    state.rewardApplied = null;
    state.rewardCode = "";
    $("#rewardCodeStatus").textContent = "";
    updateCheckoutTotals();
  }
});
$("#loginPhone").addEventListener("keydown", (event) => {
  if (event.key === "Enter") submitPhoneLogin();
});
$$('.site-nav a').forEach((link) => link.addEventListener("click", (event) => {
  event.preventDefault();
  showView("menu");
  const target = $(link.getAttribute("href"));
  setTimeout(() => target?.scrollIntoView({ behavior: "smooth", block: "start" }), 40);
}));
$("#openCheckoutBtn").addEventListener("click", openCheckout);
$("#backToMenuBtn").addEventListener("click", () => showView("menu"));
$("#submitOrderBtn").addEventListener("click", submitOrder);
$("#resumeOrderBtn").addEventListener("click", resumeOrder);
$("#uploadProofBtn").addEventListener("click", uploadProof);
$("#cancelOrderBtn").addEventListener("click", cancelOrder);
$("#copyWalletBtn").addEventListener("click", async () => {
  await navigator.clipboard.writeText(`${state.order.wallet_number} — ${state.order.total}`);
  $("#copyWalletBtn").textContent = "تم النسخ";
  setTimeout(() => { $("#copyWalletBtn").textContent = "نسخ الرقم والمبلغ"; }, 1500);
});
$("#newOrderBtn").addEventListener("click", () => {
  localStorage.removeItem("broost_active_order");
  history.replaceState(null, "", "/");
  state.order = null;
  $("#resumeOrderBtn").hidden = true;
  showView("menu");
});

["customerName", "customerPhone", "areaSelect", "customerAddress", "orderNotes"].forEach((id) => {
  $("#" + id).addEventListener("input", saveCustomerDraft);
  $("#" + id).addEventListener("change", saveCustomerDraft);
});

renderLoginState();
loadStore().then(async () => {
  restoreCustomerDraft();
  if (state.loggedPhone) {
    $("#customerPhone").value = state.loggedPhone;
    try {
      state.accountLoyalty = await api(`/api/loyalty?phone=${encodeURIComponent(state.loggedPhone)}`);
      state.loyalty = state.accountLoyalty;
      applyCustomerProfile(state.accountLoyalty, true);
    } catch {
      state.accountLoyalty = null;
    }
    renderLoginState();
    saveCustomerDraft();
    await loadCustomerOrders(false);
  }
  updateCheckoutTotals();
  if (!state.loggedPhone) loadLoyalty();
  const savedOrder = new URLSearchParams(location.search).get("order") || localStorage.getItem("broost_active_order");
  if (savedOrder) {
    localStorage.setItem("broost_active_order", savedOrder);
    $("#resumeOrderBtn").hidden = false;
    resumeOrder();
  }
});

setInterval(async () => {
  if (!state.order) return;
  try {
    state.order = await api(`/api/orders/${encodeURIComponent(state.order.resume_token)}`);
    renderOrder();
  } catch { /* keep the last known state */ }
}, 10000);

setInterval(() => {
  if (!document.hidden) loadStore();
}, 30000);
