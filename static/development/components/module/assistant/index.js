/**
 * Site chat bot widget (bottom-right). Backend: assistant/ (Django).
 *
 *  POST /api/assistant/message/                  {message, conversation_id?}
 *  GET  /api/assistant/conversations/<id>/       history
 *  POST /api/assistant/conversations/<id>/order-placed/ {token, order_number}
 *
 * The bot never places an order itself. It shows a card; the buyer's click
 * on «Підтвердити» posts the card to /api/create-order/, the same endpoint
 * the checkout form uses, so the order gets the usual Telegram card, letter,
 * stock change and GA4 events.
 */
import "./index.scss";
import { updateCountBadge } from "../../../utils/updateCountBadge";
import { trackEcommerce, trackEvent, CURRENCY } from "../../../utils/analytics";

const CONV_KEY = "mrc_assistant_conversation";
const DRAFT_KEY = "mrc_assistant_draft";
const LIMIT = 500;
const SUGGESTIONS = [
  "Підібрати килим",
  "Доставка і оплата",
  "Оформити замовлення в чаті",
];

const store = {
  get(key) {
    try {
      return window.localStorage.getItem(key);
    } catch (e) {
      return null;
    }
  },
  set(key, value) {
    try {
      if (value === null || value === undefined) window.localStorage.removeItem(key);
      else window.localStorage.setItem(key, value);
    } catch (e) {
      /* private mode */
    }
  },
};

function cookie(name) {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : "";
}

function csrfHeaders() {
  return { "X-CSRFToken": cookie("csrftoken") };
}

/** fetch with axios-like errors: rejects with {response: {status, data, headers}}. */
async function request(method, url, body) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 60000);
  try {
    const res = await fetch(url, {
      method,
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        ...(body ? { "Content-Type": "application/json" } : {}),
        ...csrfHeaders(),
      },
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
    let data = null;
    try {
      data = await res.json();
    } catch (e) {
      data = null;
    }
    if (!res.ok) {
      const headers = { "retry-after": res.headers.get("Retry-After") };
      const error = new Error(`HTTP ${res.status}`);
      error.response = { status: res.status, data: data || {}, headers };
      throw error;
    }
    return { data };
  } finally {
    clearTimeout(timer);
  }
}

const api = {
  get: (path) => request("GET", `/api/assistant${path}`),
  post: (path, body) => request("POST", `/api/assistant${path}`, body),
};

// ── tiny safe markdown: escape everything, then **bold**, [links](/x/), lists ──
function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function safeHref(url) {
  const raw = String(url || "").trim();
  if (/^\/(?!\/)/.test(raw)) return raw;
  try {
    const parsed = new URL(raw);
    if (parsed.origin === window.location.origin) return parsed.pathname + parsed.search + parsed.hash;
    if (parsed.protocol === "https:") return parsed.href;
    if (parsed.protocol === "tel:" || parsed.protocol === "mailto:") return parsed.href;
  } catch (e) {
    /* not a URL */
  }
  return null;
}

function inline(text) {
  let html = escapeHtml(text);
  html = html.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (match, label, url) => {
    const href = safeHref(url.replace(/&amp;/g, "&"));
    if (!href) return label;
    const external = /^https?:/.test(href);
    return `<a href="${escapeHtml(href)}"${external ? ' target="_blank" rel="noopener"' : ""}>${label}</a>`;
  });
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/(\+380[\d\s]{9,13}\d)/g, (m) => `<a href="tel:${m.replace(/\s/g, "")}">${m}</a>`);
  return html;
}

export function renderMarkdown(text) {
  const lines = String(text || "").split(/\n/);
  let html = "";
  let list = null;
  const closeList = () => {
    if (list) {
      html += `</${list}>`;
      list = null;
    }
  };
  lines.forEach((line) => {
    const bullet = line.match(/^\s*[-*•]\s+(.*)$/);
    const numbered = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (bullet || numbered) {
      const kind = bullet ? "ul" : "ol";
      if (list !== kind) {
        closeList();
        html += `<${kind}>`;
        list = kind;
      }
      html += `<li>${inline((bullet || numbered)[1])}</li>`;
      return;
    }
    closeList();
    if (line.trim()) html += `<p>${inline(line)}</p>`;
  });
  closeList();
  return html;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

function money(value) {
  const n = Number(value) || 0;
  return `${Math.round(n).toLocaleString("uk-UA").replace(/,/g, " ")} грн`;
}

const ICON_CHAT =
  '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20.5l1.4-4.9A8 8 0 1 1 21 12Z"/><path d="M8.5 11h.01M12 11h.01M15.5 11h.01"/></svg>';
const ICON_CLOSE =
  '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>';
const ICON_SEND =
  '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 12 7-7 7 7M12 5v15"/></svg>';

class AssistantWidget {
  constructor() {
    this.conversationId = store.get(CONV_KEY);
    this.messages = [];
    this.pendingToken = null;
    this.orderNumber = null;
    this.busy = false;
    this.loaded = false;
    this.open = false;
    this.cooldownUntil = 0;
    this.build();
  }

  build() {
    const root = el("div", "assistant-widget");
    root.innerHTML = `
      <section class="assistant-panel" id="mrc-assistant" role="dialog" aria-modal="false" aria-labelledby="mrc-assistant-title" hidden>
        <header class="assistant-header">
          <span class="assistant-avatar" aria-hidden="true">mr</span>
          <div class="assistant-header-text">
            <p class="assistant-title" id="mrc-assistant-title">Помічник mr.Carpet</p>
            <p class="assistant-status">Підберу килим і оформлю замовлення</p>
          </div>
          <button type="button" class="assistant-reset" title="Нова розмова" aria-label="Почати нову розмову">Нова</button>
          <button type="button" class="assistant-close" aria-label="Закрити чат">${ICON_CLOSE}</button>
        </header>
        <div class="assistant-log" role="log" aria-live="polite"></div>
        <form class="assistant-composer">
          <div class="assistant-input-row">
            <textarea rows="1" maxlength="${LIMIT}" placeholder="Напишіть питання…" aria-label="Ваше повідомлення" enterkeyhint="send"></textarea>
            <button type="submit" class="assistant-send" aria-label="Надіслати" disabled>${ICON_SEND}</button>
          </div>
          <p class="assistant-note">Відповідає ШІ-помічник. Ціни й наявність беремо з каталогу.</p>
        </form>
      </section>
      <button type="button" class="assistant-launcher" aria-controls="mrc-assistant" aria-expanded="false" aria-label="Відкрити чат з помічником">
        <span class="assistant-launcher-icon">${ICON_CHAT}</span>
        <span class="assistant-launcher-label">Запитати</span>
        <span class="assistant-unread" hidden>1</span>
      </button>`;
    document.body.appendChild(root);

    this.root = root;
    this.panel = root.querySelector(".assistant-panel");
    this.log = root.querySelector(".assistant-log");
    this.form = root.querySelector(".assistant-composer");
    this.input = root.querySelector("textarea");
    this.sendBtn = root.querySelector(".assistant-send");
    this.launcher = root.querySelector(".assistant-launcher");
    this.unread = root.querySelector(".assistant-unread");

    this.input.value = store.get(DRAFT_KEY) || "";
    this.launcher.addEventListener("click", () => (this.open ? this.close() : this.show()));
    root.querySelector(".assistant-close").addEventListener("click", () => this.close());
    root.querySelector(".assistant-reset").addEventListener("click", () => this.reset());
    this.form.addEventListener("submit", (e) => {
      e.preventDefault();
      this.send(this.input.value);
    });
    this.input.addEventListener("input", () => {
      store.set(DRAFT_KEY, this.input.value || null);
      this.autosize();
      this.syncSend();
    });
    this.input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
        e.preventDefault();
        this.send(this.input.value);
      }
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && this.open) this.close();
    });
    this.log.addEventListener("click", (e) => this.onLogClick(e));
  }

  autosize() {
    this.input.style.height = "auto";
    this.input.style.height = `${Math.min(this.input.scrollHeight, 120)}px`;
  }

  syncSend() {
    this.sendBtn.disabled = this.busy || !this.input.value.trim() || Date.now() < this.cooldownUntil;
  }

  async show() {
    this.open = true;
    this.panel.hidden = false;
    this.root.classList.add("is-open");
    document.body.classList.add("assistant-open");
    this.launcher.setAttribute("aria-expanded", "true");
    this.launcher.setAttribute("aria-label", "Закрити чат");
    this.unread.hidden = true;
    trackEvent("assistant_open", { page_type: window.__mrPageType || "" });
    if (!this.loaded) {
      this.loaded = true;
      await this.restore();
    }
    this.render();
    setTimeout(() => this.input.focus(), 50);
  }

  close() {
    this.open = false;
    this.panel.hidden = true;
    this.root.classList.remove("is-open");
    document.body.classList.remove("assistant-open");
    this.launcher.setAttribute("aria-expanded", "false");
    this.launcher.setAttribute("aria-label", "Відкрити чат з помічником");
  }

  reset() {
    if (this.busy) return;
    this.conversationId = null;
    store.set(CONV_KEY, null);
    this.messages = [];
    this.pendingToken = null;
    this.orderNumber = null;
    this.error = null;
    this.render();
    this.input.focus();
  }

  async restore() {
    if (!this.conversationId) return;
    try {
      const { data } = await api.get(`/conversations/${encodeURIComponent(this.conversationId)}/`);
      this.messages = data.messages || [];
      this.pendingToken = data.pending_token || null;
      this.orderNumber = data.order_number || null;
    } catch (error) {
      // Another browser session or an old id: start over quietly.
      this.conversationId = null;
      store.set(CONV_KEY, null);
      this.messages = [];
    }
  }

  async send(raw) {
    const text = String(raw || "").trim().slice(0, LIMIT);
    if (!text || this.busy || Date.now() < this.cooldownUntil) return;
    this.busy = true;
    this.error = null;
    this.messages.push({ id: `local-${Date.now()}`, role: "user", content: text });
    this.input.value = "";
    store.set(DRAFT_KEY, null);
    this.autosize();
    this.render();
    trackEvent("assistant_message", { page_type: window.__mrPageType || "" });

    try {
      const { data } = await api.post("/message/", {
        message: text,
        ...(this.conversationId ? { conversation_id: this.conversationId } : {}),
      });
      this.conversationId = data.conversation_id;
      store.set(CONV_KEY, data.conversation_id);
      this.pendingToken = data.pending_token || null;
      this.orderNumber = data.order_number || null;
      const reply = data.message || {};
      this.messages.push(reply);
      if (reply.cart_changed) this.refreshCart();
      (reply.cart_events || []).forEach((ev) => {
        if (ev.event === "add_to_cart" && ev.item) {
          trackEcommerce("add_to_cart", {
            currency: CURRENCY,
            value: (Number(ev.item.price) || 0) * (Number(ev.item.quantity) || 1),
            items: [ev.item],
          });
        }
      });
      if (!this.open) this.unread.hidden = false;
    } catch (error) {
      const status = error?.response?.status;
      const retry = Number(error?.response?.headers?.["retry-after"]) || 0;
      if (status === 429 && retry) {
        this.cooldownUntil = Date.now() + retry * 1000;
        setTimeout(() => this.syncSend(), retry * 1000 + 50);
      }
      this.error =
        error?.response?.data?.error ||
        (navigator.onLine === false
          ? "Немає інтернету. Перевірте з'єднання."
          : "Не вдалося надіслати. Спробуйте ще раз або подзвоніть нам.");
      // Let the buyer edit and resend what did not go through.
      const last = this.messages[this.messages.length - 1];
      if (last && last.role === "user" && String(last.id).startsWith("local-")) {
        this.messages.pop();
        this.input.value = text;
        this.autosize();
      }
    } finally {
      this.busy = false;
      this.render();
    }
  }

  async refreshCart() {
    try {
      const { data } = await request("GET", "/api/cart-products/");
      const count = (data || []).reduce((sum, row) => sum + (Number(row.quantity) || 0), 0);
      updateCountBadge(".header_bottom_panel_cart", count);
      window.cartProductsCount = (data || []).length;
    } catch (e) {
      /* the badge catches up on the next page */
    }
  }

  onLogClick(event) {
    const suggestion = event.target.closest("[data-suggest]");
    if (suggestion) {
      this.send(suggestion.dataset.suggest);
      return;
    }
    const confirmBtn = event.target.closest("[data-order-confirm]");
    if (confirmBtn) {
      this.confirmOrder(confirmBtn);
      return;
    }
    const editBtn = event.target.closest("[data-order-edit]");
    if (editBtn) {
      this.input.value = "Хочу змінити дані в замовленні: ";
      this.autosize();
      this.syncSend();
      this.input.focus();
      return;
    }
    const sizeBtn = event.target.closest("[data-add-size]");
    if (sizeBtn) {
      this.send(`Додай у кошик ${sizeBtn.dataset.title}, розмір ${sizeBtn.dataset.size}`);
    }
  }

  async confirmOrder(button) {
    const card = button.closest(".assistant-order");
    const order = this.findOrder(button.dataset.orderConfirm);
    if (!order || this.busy) return;
    this.busy = true;
    button.disabled = true;
    button.textContent = "Оформлюємо…";
    const errorBox = card.querySelector(".assistant-order-error");
    errorBox.textContent = "";
    try {
      const { data } = await request("POST", "/api/create-order/", {
        name: order.name,
        surname: order.surname || order.name,
        email: order.email || "",
        phone: order.phone,
        city: order.city,
        address: order.address,
        payment_type: order.payment_type,
        message: order.comment ? `Оформлено через чат-бот. ${order.comment}` : "Оформлено через чат-бот.",
      });
      const number = data?.order_number;
      trackEvent("assistant_order", { payment_type: order.payment_type });
      try {
        const placed = await api.post(
          `/conversations/${encodeURIComponent(this.conversationId)}/order-placed/`,
          { token: order.token, order_number: number }
        );
        if (placed.data?.message) this.messages.push(placed.data.message);
      } catch (e) {
        /* the order exists; the chat note is a nicety */
      }
      this.pendingToken = null;
      this.orderNumber = number;
      this.busy = false;
      this.render();
      updateCountBadge(".header_bottom_panel_cart", 0);
      const redirect = data?.redirect_url || (order.payment_type === "liqpay" ? "/payment/" : "/success/");
      setTimeout(() => {
        window.location.href = redirect;
      }, 1800);
    } catch (error) {
      this.busy = false;
      button.disabled = false;
      button.textContent = "Підтвердити";
      const data = error?.response?.data || {};
      const firstField = Object.keys(data).find((k) => Array.isArray(data[k]));
      errorBox.textContent =
        data.message || data.error || (firstField ? `${firstField}: ${data[firstField][0]}` : "") ||
        "Не вдалося оформити. Спробуйте ще раз або подзвоніть нам.";
    }
  }

  findOrder(token) {
    for (let i = this.messages.length - 1; i >= 0; i -= 1) {
      const order = this.messages[i].order;
      if (order && order.token === token) return order;
    }
    return null;
  }

  // ── rendering ──
  render() {
    this.log.textContent = "";
    if (!this.messages.length) this.log.appendChild(this.renderWelcome());
    this.messages.forEach((message) => this.log.appendChild(this.renderMessage(message)));
    if (this.busy) {
      const typing = el("div", "assistant-pending");
      typing.setAttribute("role", "status");
      typing.innerHTML = '<span class="assistant-typing" aria-hidden="true"><i></i><i></i><i></i></span><span>Шукаю відповідь…</span>';
      this.log.appendChild(typing);
    }
    if (this.error) {
      const box = el("div", "assistant-error", this.error);
      box.setAttribute("role", "alert");
      this.log.appendChild(box);
    }
    this.input.disabled = this.busy;
    this.syncSend();
    this.log.scrollTop = this.log.scrollHeight;
  }

  renderWelcome() {
    const box = el("div", "assistant-welcome");
    box.appendChild(el("p", "assistant-welcome-title", "Привіт! Допоможу обрати килим"));
    box.appendChild(
      el(
        "p",
        "assistant-welcome-text",
        "Напишіть кімнату, розмір чи колір. Можу підказати про доставку і оформити замовлення прямо тут."
      )
    );
    const list = el("div", "assistant-suggestions");
    SUGGESTIONS.forEach((text) => {
      const btn = el("button", "assistant-suggestion", text);
      btn.type = "button";
      btn.dataset.suggest = text;
      list.appendChild(btn);
    });
    box.appendChild(list);
    return box;
  }

  renderMessage(message) {
    const wrap = el("div", `assistant-message assistant-message--${message.role === "user" ? "user" : "assistant"}`);
    const bubble = el("div", "assistant-bubble");
    if (message.role === "user") bubble.textContent = message.content;
    else bubble.innerHTML = renderMarkdown(message.content);
    wrap.appendChild(bubble);
    if (message.products && message.products.length) wrap.appendChild(this.renderProducts(message.products));
    if (message.order) wrap.appendChild(this.renderOrder(message.order));
    return wrap;
  }

  renderProducts(products) {
    const row = el("div", "assistant-products");
    products.forEach((p) => {
      const card = el("div", "assistant-product");
      const link = el("a", "assistant-product-link");
      link.href = p.url;
      if (p.image) {
        const img = el("img", "assistant-product-img");
        img.src = p.image;
        img.alt = p.title;
        img.loading = "lazy";
        img.addEventListener("error", () => img.classList.add("is-broken"), { once: true });
        img.width = 120;
        img.height = 120;
        link.appendChild(img);
      }
      link.appendChild(el("span", "assistant-product-title", p.title));
      if (p.price_from) link.appendChild(el("span", "assistant-product-price", `від ${money(p.price_from)}`));
      card.appendChild(link);
      if (p.sizes && p.sizes.length) {
        const sizes = el("div", "assistant-product-sizes");
        p.sizes.slice(0, 4).forEach((s) => {
          const btn = el("button", "assistant-size", s.size);
          btn.type = "button";
          btn.title = `Додати в кошик: ${s.size}, ${money(s.price)}`;
          btn.dataset.addSize = s.size_id;
          btn.dataset.size = s.size;
          btn.dataset.title = p.title;
          sizes.appendChild(btn);
        });
        card.appendChild(sizes);
      }
      row.appendChild(card);
    });
    return row;
  }

  renderOrder(order) {
    const active = order.token && order.token === this.pendingToken;
    const card = el("div", `assistant-order${active ? "" : " is-stale"}`);
    card.appendChild(el("p", "assistant-order-title", "Перевірте замовлення"));
    const list = el("ul", "assistant-order-items");
    (order.items || []).forEach((item) => {
      const li = el("li");
      li.appendChild(el("span", "", `${item.title}, ${item.size} × ${item.quantity}`));
      li.appendChild(el("strong", "", money(item.line_total)));
      list.appendChild(li);
    });
    card.appendChild(list);
    const rows = [
      ["Разом", money(order.total)],
      ["Доставка", order.free_delivery ? "безкоштовно" : `за тарифами Нової Пошти, від ${order.delivery_from} грн`],
      ["Отримувач", `${order.name} ${order.surname}`],
      ["Телефон", order.phone],
      ["Куди", `${order.city}, ${order.address}`],
      ["Оплата", order.payment_type === "liqpay" ? "карткою онлайн" : "при отриманні"],
    ];
    if (order.email) rows.push(["Email", order.email]);
    if (order.comment) rows.push(["Коментар", order.comment]);
    const dl = el("dl", "assistant-order-details");
    rows.forEach(([k, v]) => {
      dl.appendChild(el("dt", "", k));
      dl.appendChild(el("dd", "", v));
    });
    card.appendChild(dl);
    const error = el("p", "assistant-order-error");
    error.setAttribute("role", "alert");
    card.appendChild(error);
    if (active) {
      const actions = el("div", "assistant-order-actions");
      const ok = el("button", "assistant-order-confirm", "Підтвердити");
      ok.type = "button";
      ok.dataset.orderConfirm = order.token;
      const edit = el("button", "assistant-order-edit", "Змінити");
      edit.type = "button";
      edit.dataset.orderEdit = "1";
      actions.appendChild(ok);
      actions.appendChild(edit);
      card.appendChild(actions);
    } else {
      const lastOrder = [...this.messages].reverse().find((m) => m.order)?.order;
      const placed = this.orderNumber && lastOrder === order;
      card.appendChild(
        el("p", "assistant-order-stale", placed ? `Оформлено, №${this.orderNumber}` : "Ця картка вже не активна")
      );
    }
    return card;
  }
}

function boot() {
  if (window.__mrcAssistant) return;
  window.__mrcAssistant = new AssistantWidget();
}

if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
else boot();
