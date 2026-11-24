/**
 * Page-side GA4 hooks: ecommerce funnel + UX events.
 *
 * Transport lives in the head core (templates/includes/analytics_core.html):
 * window.mrTrack / window.mrTrackEcommerce pick gtag or GTM, scrub personal
 * data and are no-ops without GA. Everything here goes through them.
 *
 * Item format is the server one (project/ga4_ecommerce.py): item_id = catalog
 * Product.pk, item_brand "mr.Carpet", item_variant = size, price = UAH unit
 * price, currency UAH on the event. Same keys everywhere, so GA4 joins
 * list → view → cart → purchase.
 *
 * `purchase` is NEVER sent from the browser: it goes server-side via the
 * Measurement Protocol (project/ga4_mp.py). A client one doubled revenue.
 */

export const CURRENCY = "UAH";
export const BRAND = "mr.Carpet";
const MAX_LIST_ITEMS = 24;

export function parseMoney(text) {
  if (text == null || text === "") return 0;
  const n = parseFloat(
    String(text)
      .replace(/[^\d.,]/g, "")
      .replace(",", ".")
  );
  return Number.isFinite(n) ? n : 0;
}

function positiveQty(...candidates) {
  for (const raw of candidates) {
    const n = Number(raw);
    if (Number.isFinite(n) && n > 0) return n;
  }
  return 1;
}

export function trackEvent(name, params = {}, opts) {
  if (!name || typeof window.mrTrack !== "function") return;
  window.mrTrack(name, params, opts);
}

export function trackEcommerce(name, payload = {}, opts) {
  if (!name || typeof window.mrTrackEcommerce !== "function") return;
  window.mrTrackEcommerce(name, { currency: CURRENCY, ...payload }, opts);
}

export function pageType() {
  return window.__mrPageType || "other";
}

/** List the element sits in: data-ga-list-id / data-ga-list-name on a wrapper. */
export function listContext(el) {
  const list = el && el.closest ? el.closest("[data-ga-list-id]") : null;
  if (!list) return null;
  return {
    el: list,
    item_list_id: list.dataset.gaListId,
    item_list_name: list.dataset.gaListName || list.dataset.gaListId,
  };
}

export function itemFromProductEl(el, overrides = {}) {
  if (!el) return null;

  const priceEl = el.querySelector(
    ".cart_item_price-value, .product_price-value, .price-value, .cart_item_price"
  );
  const activeSize = el.querySelector(".size-label.active");
  const counterVal = el.querySelector(".counter__value")?.value;
  const categoryHost = el.closest("[data-ga-item-category]");

  const base = {
    item_id: String(el.dataset.catalogProductId || el.dataset.productId || ""),
    item_name: el.dataset.productTitle || "",
    item_brand: BRAND,
    item_category:
      el.dataset.itemCategory || categoryHost?.dataset.gaItemCategory || "",
    item_variant:
      activeSize?.dataset.size?.trim() ||
      activeSize?.textContent?.trim() ||
      el.dataset.itemVariant ||
      "",
    price: parseMoney(priceEl?.textContent || el.dataset.price || "0"),
    quantity: positiveQty(counterVal, 1),
  };

  const merged = { ...base, ...overrides };
  merged.item_id = String(merged.item_id || base.item_id || "");
  merged.item_name = String(merged.item_name || "");
  merged.item_brand = merged.item_brand || BRAND;
  merged.quantity = positiveQty(merged.quantity, base.quantity, 1);
  const price = Number(merged.price);
  merged.price = Number.isFinite(price) ? Math.round(price * 100) / 100 : 0;
  if (!merged.item_category) delete merged.item_category;
  if (!merged.item_variant) delete merged.item_variant;
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
  const sum = (items || []).reduce((acc, it) => {
    const price = Number(it?.price) || 0;
    const qty = positiveQty(it?.quantity, 1);
    return acc + price * qty;
  }, 0);
  return Math.round(sum * 100) / 100;
}

/** Unique product cards of a list, in on-screen order (swiper loop clones dropped). */
function listCards(listEl) {
  const seen = new Set();
  const cards = [];
  listEl.querySelectorAll("[data-catalog-product-id]").forEach((card) => {
    const id = card.dataset.catalogProductId;
    if (!id || seen.has(id)) return;
    seen.add(id);
    cards.push(card);
  });
  return cards;
}

function listItems(listEl, ctx) {
  return listCards(listEl)
    .slice(0, MAX_LIST_ITEMS)
    .map((card, index) =>
      itemFromProductEl(card, {
        index,
        quantity: 1,
        item_list_id: ctx.item_list_id,
        item_list_name: ctx.item_list_name,
      })
    )
    .filter((it) => it && it.item_id);
}

export function trackViewItemList(listEl) {
  if (!listEl || listEl.dataset.gaSeen === "1") return;
  const ctx = listContext(listEl);
  if (!ctx) return;
  const items = listItems(listEl, ctx);
  if (!items.length) return;
  listEl.dataset.gaSeen = "1";
  trackEcommerce("view_item_list", {
    item_list_id: ctx.item_list_id,
    item_list_name: ctx.item_list_name,
    items,
  });
}

/** view_item_list when a list actually scrolls into view, not for every list on load. */
export function observeLists(root = document) {
  const lists = [...root.querySelectorAll("[data-ga-list-id]")];
  if (root !== document && root.matches?.("[data-ga-list-id]")) lists.push(root);
  if (!lists.length) return;
  if (!("IntersectionObserver" in window)) {
    lists.forEach(trackViewItemList);
    return;
  }
  const io = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        io.unobserve(entry.target);
        trackViewItemList(entry.target);
      });
    },
    { threshold: 0.2 }
  );
  lists.forEach((el) => io.observe(el));
}

function bindSelectItem() {
  document.addEventListener(
    "click",
    (e) => {
      const link = e.target.closest("a[href]");
      if (!link || !/\/catalog\/product\//.test(link.getAttribute("href") || "")) {
        return;
      }
      const card = link.closest("[data-catalog-product-id]");
      const ctx = listContext(card);
      if (!card || !ctx) return;
      const index = Math.max(0, listCards(ctx.el).indexOf(card));
      const item = itemFromProductEl(card, {
        index,
        quantity: 1,
        item_list_id: ctx.item_list_id,
        item_list_name: ctx.item_list_name,
      });
      if (!item?.item_id) return;
      trackEcommerce(
        "select_item",
        {
          item_list_id: ctx.item_list_id,
          item_list_name: ctx.item_list_name,
          items: [item],
        },
        { beforeUnload: true }
      );

      const article = card.closest("[data-article-slug]");
      if (article && /^blog_/.test(ctx.item_list_id)) {
        trackEvent(
          "blog_product_click",
          {
            article_slug: article.dataset.articleSlug,
            item_id: item.item_id,
            item_name: item.item_name,
            placement: ctx.item_list_id === "blog_sidebar" ? "sidebar" : "inline",
            index,
          },
          { beforeUnload: true }
        );
      }
    },
    true
  );
}

function contactMethod(href) {
  const h = String(href || "").trim();
  if (/^tel:/i.test(h)) return "phone";
  if (/^mailto:/i.test(h)) return "email";
  if (/t\.me\/share|facebook\.com\/sharer|^viber:\/\/forward/i.test(h)) return null;
  if (/^tg:|\/\/(t\.me|telegram\.me)\//i.test(h)) return "telegram";
  if (/^viber:|invite\.viber\.com|\/\/viber\.me\//i.test(h)) return "viber";
  if (/instagram\.com/i.test(h)) return "instagram";
  if (/facebook\.com|\/\/m\.me\//i.test(h)) return "facebook";
  if (/tiktok\.com/i.test(h)) return "tiktok";
  if (/youtube\.com|youtu\.be/i.test(h)) return "youtube";
  return null;
}

function linkLocation(el) {
  if (el.closest("header, .header")) return "header";
  if (el.closest("footer, .footer")) return "footer";
  if (el.closest(".modal-overlay, [class*='-modal']")) return "modal";
  return pageType();
}

function bindContactClicks() {
  document.addEventListener(
    "click",
    (e) => {
      const a = e.target.closest("a[href]");
      if (!a) return;
      const method = contactMethod(a.getAttribute("href"));
      if (!method) return;
      trackEvent(
        "contact",
        { method, link_location: linkLocation(a) },
        // tel:/mailto: keep the page; social links leave it.
        { beforeUnload: method !== "phone" && method !== "email" }
      );
    },
    true
  );
}

function bindCtaClicks() {
  document.addEventListener("click", (e) => {
    // Not add-to-cart (has add_to_cart) and not the checkout submit (checkout_submit).
    const cta = e.target.closest(
      ".basket__confirm-order-btn a, .basket__empty-btn, .success__back-to-main-btn a"
    );
    if (!cta) return;
    const label =
      (cta.textContent || "").trim().slice(0, 80) ||
      cta.getAttribute("title") ||
      "cta";
    trackEvent(
      "cta_click",
      {
        cta_label: label,
        cta_href: cta.getAttribute("href") || window.location.pathname,
      },
      { beforeUnload: true }
    );
  });
}

// ---- checkout steps ------------------------------------------------------

const sentShipping = {};
const sentPayment = {};

function cartData() {
  return readJsonScript("ga4-cart-data") || {};
}

export function paymentTypeFromInput(input) {
  if (!input) return "cash";
  return input.id === "card" ? "liqpay" : "cash";
}

function shippingTierFromDom() {
  const select = document.getElementById("nova-post-warehouse-select");
  if (!select || !select.value) return "";
  const option = select.options[select.selectedIndex];
  const text = (option && option.text) || "";
  return /поштомат/i.test(text) ? "nova_poshta_postomat" : "nova_poshta_branch";
}

export function trackShippingInfo(tier) {
  if (!tier || sentShipping[tier]) return;
  sentShipping[tier] = true;
  const c = cartData();
  trackEcommerce("add_shipping_info", {
    value: c.value || 0,
    shipping_tier: tier,
    items: c.items || [],
  });
}

export function trackPaymentInfo(paymentType) {
  if (!paymentType || sentPayment[paymentType]) return;
  sentPayment[paymentType] = true;
  const c = cartData();
  trackEcommerce("add_payment_info", {
    value: c.value || 0,
    payment_type: paymentType,
    items: c.items || [],
  });
}

/** Valid checkout form sent: close the funnel steps a user skipped (defaults). */
export function trackCheckoutSubmit(paymentType) {
  const tier = shippingTierFromDom();
  if (tier && !Object.keys(sentShipping).length) trackShippingInfo(tier);
  if (!Object.keys(sentPayment).length) trackPaymentInfo(paymentType);
  const c = cartData();
  trackEvent("checkout_submit", {
    payment_type: paymentType,
    shipping_tier: tier,
    value: c.value || 0,
    currency: CURRENCY,
  });
}

let formErrorCount = 0;
/** Field names only, never what was typed. */
export function trackFormError(formName, fields, extra = {}) {
  const list = [...new Set((fields || []).filter(Boolean).map(String))];
  if (!list.length || formErrorCount >= 10) return;
  formErrorCount += 1;
  trackEvent("form_error", {
    form_name: formName,
    error_fields: list.join(",").slice(0, 100),
    error_count: list.length,
    ...extra,
  });
}

function bindCheckoutSteps() {
  if (pageType() !== "checkout") return;

  document.addEventListener("change", (e) => {
    const t = e.target;
    if (t && t.id === "nova-post-warehouse-select" && t.value) {
      trackShippingInfo(shippingTierFromDom());
    }
    if (t instanceof HTMLInputElement && t.name === "payment" && t.checked) {
      trackPaymentInfo(paymentTypeFromInput(t));
    }
  });

  // The payment accordion sets `checked` from code, so no change event fires.
  document.addEventListener("click", (e) => {
    const item = e.target.closest(".basket__payment-item");
    if (!item) return;
    const input = item.querySelector('input[name="payment"]');
    if (input && !input.disabled) trackPaymentInfo(paymentTypeFromInput(input));
  });
}

// ---- misc ---------------------------------------------------------------

function bindShareClicks() {
  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".bl-share__btn, [data-share-method]");
    if (!btn) return;
    let method = btn.dataset.shareMethod || "";
    if (!method) {
      const m = btn.className.match(/bl-share__btn--([a-z]+)/);
      method = m ? m[1] : "other";
    }
    if (method === "copy") method = "copy_link";
    const article = btn.closest("[data-article-slug]");
    trackEvent("share", {
      method,
      content_type: article ? "article" : pageType(),
      item_id: article ? article.dataset.articleSlug : window.location.pathname,
    });
  });
}

export function bindGlobalAnalyticsHooks() {
  if (window.__mrAnalyticsHooksBound) return;
  window.__mrAnalyticsHooksBound = true;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => observeLists());
  } else {
    observeLists();
  }

  bindSelectItem();
  bindContactClicks();
  bindCtaClicks();
  bindCheckoutSteps();
  bindShareClicks();
}

const api = {
  trackEvent,
  trackEcommerce,
  itemFromProductEl,
  parseMoney,
  readJsonScript,
  itemsValue,
  observeLists,
  trackFormError,
  CURRENCY,
  BRAND,
};

window.mrAnalytics = api;
bindGlobalAnalyticsHooks();

export default api;
