import test from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { readFileSync } from "node:fs";

// Exercise the real loading/rendering functions with deterministic API responses.
const source = readFileSync(new URL("../webapp/static/admin.js", import.meta.url), "utf8");
const functions = source.slice(0, source.indexOf("$$('[data-admin-view]')"));
function harness(handler) {
  const elements = new Map();
  const get = (id) => {
    if (!elements.has(id)) elements.set(id, { value: "", hidden: true, style: {}, innerHTML: "", textContent: "" });
    return elements.get(id);
  };
  get("#ordersDaySelect").value = "ALL";
  const context = vm.createContext({
    console: { error() {} }, URLSearchParams, Date, Set,
    sessionStorage: { getItem() { return ""; }, removeItem() {} },
    window: { BROOST_CONFIG: { apiBaseUrl: "https://api.example.test" } },
    document: { querySelector: get, querySelectorAll() { return []; } },
    fetch: async (url) => {
      const data = handler(url);
      return { ok: true, status: 200, json: async () => data };
    },
  });
  vm.runInContext(functions, context);
  return { context, get, run: (code) => vm.runInContext(code, context) };
}

test("all days retrieves unfiltered history including closed orders and every page", async () => {
  const urls = [];
  const h = harness((url) => {
    urls.push(url);
    if (url.includes("business-day")) return {};
    if (url.includes("date_from")) return [];
    const offset = Number(new URL(url).searchParams.get("offset"));
    return Array.from({ length: offset === 0 ? 500 : 1 }, (_, i) => ({
      id: offset + i + 1, source: "POS", status: "COMPLETED", total: 50,
      public_number: `POS-${offset + i + 1}`, created_at: "2026-08-01 12:00:00", items: [],
    }));
  });
  await h.run("loadOrders()");
  assert.equal(h.run("adminState.orders.length"), 501);
  assert(urls.some((url) => url.includes("offset=500") && !url.includes("date_from")));
  assert.match(h.get("#closedOrdersTable").innerHTML, /data-order-details="501"/);
});

test("failed refresh preserves last good orders and shows an error instead of empty results", async () => {
  const h = harness(() => { throw new Error("server unavailable"); });
  h.run("adminState.orders = [{id: 42}]");
  await assert.rejects(h.run("loadOrders()"), /server unavailable/);
  assert.equal(h.run("adminState.orders[0].id"), 42);
  assert.equal(h.get("#ordersError").hidden, false);
  assert.match(h.get("#adminConnection").className, /danger/);
});

test("source filter applies to the full history", async () => {
  const urls = [];
  const h = harness((url) => { urls.push(url); return url.includes("business-day") ? {} : []; });
  h.get("#ordersSource").value = "POS";
  await h.run("loadOrders()");
  assert(urls.some((url) => url.includes("source=POS") && !url.includes("date_from")));
});

test("order details include invoice lines, staff, notes and discounts with HTML escaped", () => {
  const h = harness(() => []);
  h.run(`adminState.orders = [{id: 7, public_number: "POS-7", source: "POS", status: "COMPLETED",
    cashier_name: "Cashier", driver_name: "Driver", customer_name: "<script>bad</script>",
    notes: "No salt", subtotal: 100, discount: 10, delivery_fee: 15, total: 105,
    items: [{item_name: "Meal", size_name: "Large", quantity: 2, unit_price: 50,
      extras: [{name: "Sauce", price: 5}]}]}]; openOrderDetails(7)`);
  const html = h.get("#orderDetailsBody").innerHTML;
  for (const value of ["Cashier", "Driver", "No salt", "Meal", "Large", "Sauce", "الخصم", "الإجمالي النهائي"]) assert(html.includes(value));
  assert(!html.includes("<script>"));
  assert(html.includes("&lt;script&gt;"));
  assert.equal(h.get("#orderDetailsModal").hidden, false);
});
