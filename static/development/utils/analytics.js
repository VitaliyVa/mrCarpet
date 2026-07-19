/**
 * GA4 / GTM dual push (dataLayer + gtag).
 * No-op when tags absent. Hooks bind once per page.
 */

export const CURRENCY = "UAH";
export const BRAND = "mr.Carpet";

function ensureDataLayer() {
  window.dataLayer = window.dataLayer || [];
  return window.dataLayer;
}

export function parseMoney(text) {
  if (text == null || text === "") return 0;
  const n = parseFloat(String(text).replace(/[^\d.,]/g, "").replace(",", "."));
  return Number.isFinite(n) ? n : 0;
}

function positiveQty(...candidates) {
  for (const raw of candidates) {
    const n = Number(raw);
    if (Number.isFinite(n) && n > 0) return n;
  }
  return 1;
}

export function trackEvent(name, params = {}) {
  if (!name) return;
  const safe = { ...params };
  ensureDataLayer().push({ event: name, ...safe });
  callGtag("event", name, safe);
}

export function trackEcommerce(name, ecommerce = {}) {
  if (!name) return;
  const payload = {
    currency: ecommerce.currency || CURRENCY,
    ...ecommerce,
  };
  if (payload.value != null) {
    const v = Number(payload.value);
    payload.value = Number.isFinite(v) ? v : 0;
  }
  // Ensure items is a real array for GA4 validation.
  if (payload.items && !Array.isArray(payload.items)) {
    payload.items = [];
  }
  const dl = ensureDataLayer();
  // Clear previous ecommerce object (GTM pattern).
  dl.push({ ecommerce: null });
  dl.push({ event: name, ecommerce: payload });
  // gtag expects flat event params (items/value/currency at top level).
  callGtag("event", name, payload);
}

/** gtag stub from head may exist; real library loads async — queue until ready. */
function callGtag(command, name, params) {
  const run = () => {
    if (typeof window.gtag === "function") {
      window.gtag(command, name, params);
      return true;
    }
    return false;
  };
  if (run()) return;
  let attempts = 0;
  const timer = setInterval(() => {
    attempts += 1;
    if (run() || attempts >= 40) clearInterval(timer);
  }, 250);
}

export function itemFromProductEl(el, overrides = {}) {
  if (!el) return null;

  const priceEl = el.querySelector(
    ".cart_item_price-value, .product_price-value, .price-value, .cart_item_price"
  );
  const activeSize = el.querySelector(".size-label.active");
  const counterVal = el.querySelector(".counter__value")?.value;

  const base = {
    item_id: String(
      el.dataset.catalogProductId || el.dataset.productId || ""
    ),
    item_name: el.dataset.productTitle || "",
    item_brand: BRAND,
    item_category: el.dataset.itemCategory || "",
    item_variant:
      activeSize?.textContent?.trim() || el.dataset.itemVariant || "",
    price: parseMoney(priceEl?.textContent || el.dataset.price || "0"),
    quantity: positiveQty(counterVal, 1),
  };

  const merged = { ...base, ...overrides };
  merged.item_id = String(merged.item_id || base.item_id || "");
  merged.item_name = String(merged.item_name || "");
  merged.item_brand = merged.item_brand || BRAND;
  merged.quantity = positiveQty(merged.quantity, base.quantity, 1);
  const price = Number(merged.price);
  merged.price = Number.isFinite(price) ? price : 0;
  return merged;
}

export function readJsonScript(id) {
  const el = document.getElementById(id);
  if (!el?.textContent) return null;
  try {
    return JSON.parse(el.textContent);
  } catch {
    return null;
  }
}

export function itemsValue(items) {
  return (items || []).reduce((sum, it) => {
    const price = Number(it?.price) || 0;
    const qty = positiveQty(it?.quantity, 1);
    return sum + price * qty;
  }, 0);
}

function markPurchaseSent(transactionId) {
  if (!transactionId) return false;
  const key = `ga4_purchase_${transactionId}`;
  try {
    if (sessionStorage.getItem(key)) return false;
    sessionStorage.setItem(key, "1");
    return true;
  } catch {
    // Private mode: fall back to in-memory guard for this navigation.
    window.__ga4PurchaseSent = window.__ga4PurchaseSent || {};
    if (window.__ga4PurchaseSent[key]) return false;
    window.__ga4PurchaseSent[key] = true;
    return true;
  }
}

function trackPurchaseFromPage() {
  const purchase = readJsonScript("ga4-purchase-data");
  if (!purchase?.transaction_id) return;
  if (!markPurchaseSent(purchase.transaction_id)) return;
  trackEcommerce("purchase", purchase);
}

function markGa4Once(key) {
  if (!key) return false;
  try {
    if (sessionStorage.getItem(key)) return false;
    sessionStorage.setItem(key, "1");
    return true;
  } catch {
    return true;
  }
}

function trackViewCartOrCheckout() {
  // Prefer inline template event (ga4_cart_event.html); this is a fallback.
  const cart = readJsonScript("ga4-cart-data");
  if (!cart?.items?.length) return;

  const path = (window.location.pathname || "/").replace(/\/+$/, "") || "/";
  if (path === "/cart") {
    if (!markGa4Once("ga4_view_cart")) return;
    trackEcommerce("view_cart", cart);
  } else if (path === "/checkout") {
    if (!markGa4Once("ga4_begin_checkout")) return;
    trackEcommerce("begin_checkout", cart);
  }
}

function bindBeginCheckoutCta() {
  // Fire when leaving cart toward checkout (pageview alone can be missed).
  document.addEventListener("click", (e) => {
    const link = e.target.closest('a[href*="/checkout"]');
    if (!link) return;
    const cart = readJsonScript("ga4-cart-data");
    if (!cart?.items?.length) return;
    if (!markGa4Once("ga4_begin_checkout")) return;
    trackEcommerce("begin_checkout", cart);
  });
}

function trackViewItemList() {
  const path = window.location.pathname;
  const isList =
    path === "/" ||
    path.startsWith("/catalog") ||
    path.startsWith("/favourites") ||
    path.startsWith("/favorites");
  if (!isList) return;

  const cards = [
    ...document.querySelectorAll(
      ".cart_item[data-catalog-product-id], .product[data-catalog-product-id]"
    ),
  ].slice(0, 24);
  if (!cards.length) return;

  const items = cards
    .map((el, index) => {
      const item = itemFromProductEl(el, { index });
      return item?.item_id ? item : null;
    })
    .filter(Boolean);

  if (!items.length) return;

  trackEcommerce("view_item_list", {
    item_list_id: path,
    item_list_name: document.title || path,
    items,
  });
}

function bindSelectItem() {
  document.addEventListener("click", (e) => {
    // Only PDP links — avoid basket/utility anchors.
    const link = e.target.closest('a[href*="/catalog/product/"]');
    if (!link) return;
    const card =
      link.closest(".cart_item, .product, .header__search-product") || link;
    const item = itemFromProductEl(card);
    if (!item?.item_id) return;
    trackEcommerce("select_item", {
      item_list_id: window.location.pathname,
      item_list_name: document.title || "",
      items: [item],
    });
  });
}

function bindContactClicks() {
  document.addEventListener("click", (e) => {
    const a = e.target.closest('a[href^="tel:"], a[href^="mailto:"]');
    if (!a) return;
    const href = a.getAttribute("href") || "";
    if (href.startsWith("tel:")) {
      trackEvent("click_phone", {
        link_url: href.slice(0, 64),
        link_text: (a.textContent || "").trim().slice(0, 64),
      });
    } else if (href.startsWith("mailto:")) {
      trackEvent("click_email", {
        link_url: href.slice(0, 128),
        link_text: (a.textContent || "").trim().slice(0, 64),
      });
    }
  });
}

function bindCtaClicks() {
  document.addEventListener("click", (e) => {
    // Do NOT include add-to-cart — that already has add_to_cart ecommerce.
    const cta = e.target.closest(
      ".basket__confirm-order-btn a, .basket__to-order-btn, .basket__empty-btn, .success__back-to-main-btn a"
    );
    if (!cta) return;
    const label =
      (cta.textContent || "").trim().slice(0, 80) ||
      cta.getAttribute("title") ||
      "cta";
    trackEvent("cta_click", {
      cta_label: label,
      cta_href: cta.getAttribute("href") || window.location.pathname,
    });
  });
}

function bindCheckoutExtras() {
  if (!window.location.pathname.includes("/checkout")) return;

  let shippingSent = false;
  let paymentSent = false;
  const cart = () => readJsonScript("ga4-cart-data") || {};

  function firePaymentInfo(input) {
    if (paymentSent || !input) return;
    paymentSent = true;
    const c = cart();
    trackEcommerce("add_payment_info", {
      currency: c.currency || CURRENCY,
      value: c.value || 0,
      payment_type: input.id || input.value || "cash",
      items: c.items || [],
    });
  }

  // Default cash (or any pre-checked method) — do not wait for change.
  const preselected =
    document.querySelector('input[name="payment"]:checked:not(:disabled)') ||
    document.getElementById("cash");
  firePaymentInfo(preselected);

  document.addEventListener("click", (e) => {
    if (
      shippingSent ||
      !e.target.closest(
        ".basket__delivery .accordion__title, .basket__delivery-items"
      )
    ) {
      return;
    }
    shippingSent = true;
    const c = cart();
    trackEcommerce("add_shipping_info", {
      currency: c.currency || CURRENCY,
      value: c.value || 0,
      shipping_tier: "nova_poshta",
      items: c.items || [],
    });
  });

  document.addEventListener("change", (e) => {
    const input = e.target;
    if (!(input instanceof HTMLInputElement)) return;
    if (input.name !== "payment") return;
    // User switched method after default — fire again with new payment_type.
    paymentSent = false;
    firePaymentInfo(input);
  });
}

export function bindGlobalAnalyticsHooks() {
  if (window.__mrAnalyticsHooksBound) return;
  window.__mrAnalyticsHooksBound = true;

  const runPageHooks = () => {
    trackPurchaseFromPage();
    trackViewCartOrCheckout();
    trackViewItemList();
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", runPageHooks);
  } else {
    runPageHooks();
  }

  bindSelectItem();
  bindContactClicks();
  bindCtaClicks();
  bindCheckoutExtras();
  bindBeginCheckoutCta();
}

const api = {
  trackEvent,
  trackEcommerce,
  itemFromProductEl,
  parseMoney,
  readJsonScript,
  itemsValue,
  markPurchaseSent,
  CURRENCY,
  BRAND,
};

window.mrAnalytics = api;
bindGlobalAnalyticsHooks();

export default api;
