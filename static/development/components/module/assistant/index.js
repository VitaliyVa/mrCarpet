/**
 * Site chat bot widget (bottom-right). Backend: assistant/ (Django).
 *
 *  GET  /api/assistant/config/                   category tiles for the picker
 *  POST /api/assistant/message/                  {message, conversation_id?}
 *  GET  /api/assistant/conversations/<id>/       history
 *  POST /api/assistant/conversations/<id>/order-placed/ {token, order_number}
 *
 * The bot never places an order itself. It shows a card; the buyer's click
 * on «Підтвердити» posts the card to /api/create-order/, the same endpoint
 * the checkout form uses, so the order gets the usual Telegram card, letter,
 * stock change and GA4 events.
 *
 * Extras: expand to a big window, drag-resize from the top-left corner,
 * sync between tabs (localStorage "storage" events), and recovery of a
 * message whose reply never arrived (page closed, network dropped).
 */
import "./index.scss";
import { updateCountBadge } from "../../../utils/updateCountBadge";
import { trackEcommerce, trackEvent, CURRENCY } from "../../../utils/analytics";

const KEYS = {
  conv: "mrc_assistant_conversation",
  draft: "mrc_assistant_draft",
  size: "mrc_assistant_size",
  sync: "mrc_assistant_sync",
  inflight: "mrc_assistant_inflight",
  teaser: "mrc_assistant_teaser",
};
const LIMIT = 500;
const MIN_W = 340;
const MIN_H = 460;
const PICK_RUG = "Підібрати килим";
const SUGGESTIONS = [
  { text: PICK_RUG, icon: "rug" },
  { text: "Доставка і оплата", icon: "truck" },
  { text: "Оформити замовлення в чаті", icon: "bag" },
];
const THINKING = ["Шукаю в каталозі…", "Перевіряю наявність…", "Підбираю варіанти…"];
const TAB_ID = Math.random().toString(36).slice(2);
const reduceMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const isPhone = () => window.matchMedia("(max-width: 520px)").matches;

const local = {
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
  json(key) {
    try {
      return JSON.parse(this.get(key) || "null");
    } catch (e) {
      return null;
    }
  },
};

function cookie(name) {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : "";
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
        "X-CSRFToken": cookie("csrftoken"),
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
      const error = new Error(`HTTP ${res.status}`);
      error.response = { status: res.status, data: data || {}, headers: { "retry-after": res.headers.get("Retry-After") } };
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
    // Only our own pages, phone and email: a reply can never send the buyer
    // to an outside site, even if someone talks the model into writing one.
    if (parsed.origin === window.location.origin) return parsed.pathname + parsed.search + parsed.hash;
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
    return href ? `<a href="${escapeHtml(href)}">${label}</a>` : label;
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
  const n = Math.round(Number(value) || 0);
  return `${String(n).replace(/\B(?=(\d{3})+(?!\d))/g, " ")} грн`;
}

const ICONS = {
  chat: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.4 8.4 0 0 1-12.3 7.4L4 20l1.2-4.4A8.5 8.5 0 1 1 21 11.5Z"/><path d="M8.6 11.5h.01M12.2 11.5h.01M15.8 11.5h.01" stroke-width="2.6"/></svg>',
  close: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6 6 18"/></svg>',
  send: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M5.5 11.5 12 5l6.5 6.5"/></svg>',
  expand: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7"/></svg>',
  shrink: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M20 10h-6V4M4 14h6v6M14 10l7-7M10 14l-7 7"/></svg>',
  reset: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M4 12a8 8 0 1 0 2.4-5.7"/><path d="M4 4v5h5"/></svg>',
  left: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 6-6 6 6 6"/></svg>',
  right: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 6 6 6-6 6"/></svg>',
  plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 5v14M5 12h14"/></svg>',
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>',
  rug: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="3" width="14" height="18" rx="1.5"/><rect x="8" y="6" width="8" height="12" rx="1"/><path d="M5 1.5v1.5M9 1.5v1.5M15 1.5v1.5M19 1.5v1.5M5 21v1.5M9 21v1.5M15 21v1.5M19 21v1.5"/></svg>',
  truck: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h11v10H3zM14 9h4l3 3v4h-7"/><circle cx="7" cy="17.5" r="1.8"/><circle cx="17" cy="17.5" r="1.8"/></svg>',
  bag: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M5 8h14l-1 12H6L5 8Z"/><path d="M9 8V6.5a3 3 0 0 1 6 0V8"/></svg>',
  grip: '<svg viewBox="0 0 12 12" fill="currentColor"><circle cx="2" cy="2" r="1.1"/><circle cx="6" cy="2" r="1.1"/><circle cx="2" cy="6" r="1.1"/></svg>',
};

/** Horizontal slider: hidden scrollbar, arrow buttons while there is more to see. */
function makeSlider(className, items) {
  const wrap = el("div", `assistant-slider ${className}`);
  const track = el("div", "assistant-slider-track");
  items.forEach((item) => track.appendChild(item));
  const prev = el("button", "assistant-slider-arrow is-prev");
  const next = el("button", "assistant-slider-arrow is-next");
  prev.type = next.type = "button";
  prev.innerHTML = ICONS.left;
  next.innerHTML = ICONS.right;
  prev.setAttribute("aria-label", "Назад");
  next.setAttribute("aria-label", "Далі");
  prev.tabIndex = next.tabIndex = -1;
  const sync = () => {
    const max = track.scrollWidth - track.clientWidth;
    wrap.classList.toggle("can-prev", track.scrollLeft > 4);
    wrap.classList.toggle("can-next", track.scrollLeft < max - 4);
  };
  const step = (dir) => track.scrollBy({ left: dir * Math.max(160, track.clientWidth * 0.8), behavior: reduceMotion() ? "auto" : "smooth" });
  prev.addEventListener("click", () => step(-1));
  next.addEventListener("click", () => step(1));
  track.addEventListener("scroll", sync, { passive: true });
  // Mouse wheel scrolls the row sideways on desktop.
  track.addEventListener(
    "wheel",
    (e) => {
      if (Math.abs(e.deltaY) > Math.abs(e.deltaX) && track.scrollWidth > track.clientWidth) {
        const before = track.scrollLeft;
        track.scrollLeft += e.deltaY;
        if (track.scrollLeft !== before) e.preventDefault();
      }
    },
    { passive: false }
  );
  if (window.ResizeObserver) new ResizeObserver(sync).observe(track);
  requestAnimationFrame(sync);
  track.querySelectorAll("img").forEach((img) => img.addEventListener("load", sync, { once: true }));
  wrap.append(prev, track, next);
  return wrap;
}

function rugImage(src, alt, className) {
  const box = el("span", className);
  if (src) {
    const img = el("img");
    img.src = src;
    img.alt = alt || "";
    img.loading = "lazy";
    img.decoding = "async";
    img.addEventListener("load", () => box.classList.add("is-loaded"), { once: true });
    img.addEventListener("error", () => box.classList.add("is-broken"), { once: true });
    box.appendChild(img);
  } else {
    box.classList.add("is-broken");
  }
  return box;
}

class AssistantWidget {
  constructor() {
    this.conversationId = local.get(KEYS.conv);
    this.messages = [];
    this.pendingToken = null;
    this.orderNumber = null;
    this.busy = false;
    this.loaded = false;
    this.open = false;
    this.expanded = false;
    this.picker = null; // "categories" | null
    this.categories = null;
    this.cooldownUntil = 0;
    this.renderedCount = 0;
    this.recovery = null;
    this.build();
    this.bindSync();
    this.scheduleTeaser();
  }

  // ── DOM ──
  build() {
    const root = el("div", "assistant-widget");
    root.innerHTML = `
      <section class="assistant-panel" id="mrc-assistant" role="dialog" aria-modal="false" aria-labelledby="mrc-assistant-title" hidden>
        <button type="button" class="assistant-resize" aria-label="Змінити розмір вікна" title="Потягніть, щоб змінити розмір. Подвійний клік: звичайний розмір">${ICONS.grip}</button>
        <header class="assistant-header">
          <span class="assistant-avatar" aria-hidden="true"><span>mr</span><i class="assistant-online"></i></span>
          <div class="assistant-header-text">
            <p class="assistant-title" id="mrc-assistant-title">Помічник mr.Carpet</p>
            <p class="assistant-status">Онлайн · підберу килим і оформлю замовлення</p>
          </div>
          <div class="assistant-header-actions">
            <button type="button" class="assistant-icon-btn assistant-reset" aria-label="Нова розмова" title="Нова розмова">${ICONS.reset}</button>
            <button type="button" class="assistant-icon-btn assistant-expand" aria-label="Розгорнути" title="Розгорнути">${ICONS.expand}</button>
            <button type="button" class="assistant-icon-btn assistant-close" aria-label="Закрити чат" title="Закрити">${ICONS.close}</button>
          </div>
        </header>
        <div class="assistant-body">
          <div class="assistant-log" role="log" aria-live="polite"></div>
          <button type="button" class="assistant-latest" hidden>Нові повідомлення ↓</button>
        </div>
        <div class="assistant-picker" hidden></div>
        <form class="assistant-composer">
          <div class="assistant-field">
            <textarea rows="1" maxlength="${LIMIT}" placeholder="Напишіть питання…" aria-label="Ваше повідомлення" enterkeyhint="send"></textarea>
            <button type="submit" class="assistant-send" aria-label="Надіслати" disabled>${ICONS.send}</button>
          </div>
          <p class="assistant-note">ШІ-помічник. Ціни й наявність беремо з каталогу.</p>
        </form>
      </section>
      <div class="assistant-teaser" hidden>
        <button type="button" class="assistant-teaser-text">Привіт! Допомогти підібрати килим? 👋</button>
        <button type="button" class="assistant-teaser-close" aria-label="Сховати">${ICONS.close}</button>
      </div>
      <button type="button" class="assistant-launcher" aria-controls="mrc-assistant" aria-expanded="false" aria-label="Відкрити чат з помічником">
        <span class="assistant-launcher-icon">${ICONS.chat}</span>
        <span class="assistant-launcher-label">Запитати</span>
        <span class="assistant-unread" hidden>1</span>
      </button>`;
    document.body.appendChild(root);

    const $ = (s) => root.querySelector(s);
    this.root = root;
    this.panel = $(".assistant-panel");
    this.log = $(".assistant-log");
    this.latestBtn = $(".assistant-latest");
    this.pickerBox = $(".assistant-picker");
    this.form = $(".assistant-composer");
    this.input = $("textarea");
    this.sendBtn = $(".assistant-send");
    this.launcher = $(".assistant-launcher");
    this.unread = $(".assistant-unread");
    this.expandBtn = $(".assistant-expand");
    this.teaser = $(".assistant-teaser");

    this.input.value = local.get(KEYS.draft) || "";
    this.launcher.addEventListener("click", () => (this.open ? this.close() : this.show()));
    $(".assistant-close").addEventListener("click", () => this.close());
    $(".assistant-reset").addEventListener("click", () => this.reset());
    this.expandBtn.addEventListener("click", () => this.toggleExpand());
    this.form.addEventListener("submit", (e) => {
      e.preventDefault();
      this.send(this.input.value, { fromInput: true });
    });
    this.input.addEventListener("input", () => {
      local.set(KEYS.draft, this.input.value || null);
      this.autosize();
      this.syncSend();
    });
    this.input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
        e.preventDefault();
        this.send(this.input.value, { fromInput: true });
      }
    });
    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape" || !this.open) return;
      if (this.expanded) this.toggleExpand(false);
      else this.close();
    });
    this.root.addEventListener("click", (e) => {
      // A click on the dimmed page (the root's ::before) collapses the big window.
      if (e.target === this.root && this.expanded) {
        this.toggleExpand(false);
        return;
      }
      this.onClick(e);
    });
    this.log.addEventListener("scroll", () => {
      if (this.nearBottom()) this.latestBtn.hidden = true;
    }, { passive: true });
    this.latestBtn.addEventListener("click", () => this.scrollToBottom(true));
    $(".assistant-teaser-text").addEventListener("click", () => {
      this.hideTeaser(true);
      this.show();
    });
    $(".assistant-teaser-close").addEventListener("click", () => this.hideTeaser(true));
    this.bindResize($(".assistant-resize"));
    this.applySize(local.json(KEYS.size));
    this.autosize();
  }

  // ── open / close (animated) ──
  async show() {
    if (this.open) return;
    this.open = true;
    this.hideTeaser(false);
    this.panel.hidden = false;
    this.root.classList.add("is-open", "was-opened");
    this.root.classList.remove("is-closing");
    document.body.classList.add("assistant-open");
    this.launcher.setAttribute("aria-expanded", "true");
    this.unread.hidden = true;
    trackEvent("assistant_open", { page_type: window.__mrPageType || "" });
    if (!this.loaded) {
      this.loaded = true;
      this.renderedCount = 0;
      this.render();
      await this.restore();
    }
    this.render();
    this.scrollToBottom(false);
    if (!isPhone()) setTimeout(() => this.input.focus({ preventScroll: true }), 120);
  }

  close() {
    if (!this.open) return;
    this.open = false;
    this.launcher.setAttribute("aria-expanded", "false");
    document.body.classList.remove("assistant-open");
    const done = () => {
      if (this.open) return;
      this.panel.hidden = true;
      this.root.classList.remove("is-open", "is-closing");
    };
    if (reduceMotion()) return done();
    this.root.classList.add("is-closing");
    setTimeout(done, 230);
  }

  toggleExpand(force) {
    this.expanded = typeof force === "boolean" ? force : !this.expanded;
    this.root.classList.toggle("is-expanded", this.expanded);
    this.expandBtn.innerHTML = this.expanded ? ICONS.shrink : ICONS.expand;
    this.expandBtn.setAttribute("aria-label", this.expanded ? "Згорнути" : "Розгорнути");
    this.expandBtn.title = this.expanded ? "Згорнути" : "Розгорнути";
    setTimeout(() => this.scrollToBottom(false), 320);
  }

  // ── resize from the top-left corner (the window sits bottom-right) ──
  bindResize(handle) {
    let start = null;
    const move = (e) => {
      if (!start) return;
      const maxW = window.innerWidth - 48;
      const maxH = window.innerHeight - 48;
      const w = Math.min(maxW, Math.max(MIN_W, start.w + (start.x - e.clientX)));
      const h = Math.min(maxH, Math.max(MIN_H, start.h + (start.y - e.clientY)));
      start.last = { w: Math.round(w), h: Math.round(h) };
      this.applySize(start.last);
    };
    const up = () => {
      if (!start) return;
      const last = start.last;
      start = null;
      this.root.classList.remove("is-resizing");
      document.removeEventListener("pointermove", move);
      document.removeEventListener("pointerup", up);
      if (last) local.set(KEYS.size, JSON.stringify(last));
    };
    handle.addEventListener("pointerdown", (e) => {
      if (isPhone() || this.expanded) return;
      e.preventDefault();
      const r = this.panel.getBoundingClientRect();
      start = { x: e.clientX, y: e.clientY, w: r.width, h: r.height };
      this.root.classList.add("is-resizing");
      document.addEventListener("pointermove", move);
      document.addEventListener("pointerup", up);
    });
    handle.addEventListener("dblclick", () => {
      local.set(KEYS.size, null);
      this.applySize(null);
    });
  }

  applySize(size) {
    if (size && size.w && size.h) {
      this.panel.style.setProperty("--assistant-w", `${size.w}px`);
      this.panel.style.setProperty("--assistant-h", `${size.h}px`);
    } else {
      this.panel.style.removeProperty("--assistant-w");
      this.panel.style.removeProperty("--assistant-h");
    }
  }

  // ── teaser bubble near the launcher, once per visit ──
  scheduleTeaser() {
    let seen = null;
    try {
      seen = window.sessionStorage.getItem(KEYS.teaser);
    } catch (e) {
      seen = "1";
    }
    if (seen || local.get(KEYS.conv) || /\/(checkout|success|payment)\//.test(window.location.pathname)) return;
    this.teaserTimer = setTimeout(() => {
      if (this.open) return;
      this.teaser.hidden = false;
      requestAnimationFrame(() => this.teaser.classList.add("is-visible"));
    }, 9000);
  }

  hideTeaser(remember) {
    clearTimeout(this.teaserTimer);
    if (remember) {
      try {
        window.sessionStorage.setItem(KEYS.teaser, "1");
      } catch (e) {
        /* ignore */
      }
    }
    if (this.teaser.hidden) return;
    this.teaser.classList.remove("is-visible");
    setTimeout(() => {
      this.teaser.hidden = true;
    }, 250);
  }

  // ── sync between tabs ──
  broadcast() {
    local.set(KEYS.sync, JSON.stringify({ conv: this.conversationId, tab: TAB_ID, ts: Date.now() }));
  }

  bindSync() {
    window.addEventListener("storage", async (e) => {
      if (e.key !== KEYS.sync || !e.newValue) return;
      let info = null;
      try {
        info = JSON.parse(e.newValue);
      } catch (err) {
        return;
      }
      if (!info || info.tab === TAB_ID) return;
      this.conversationId = info.conv || null;
      if (!this.conversationId) {
        this.recovery = null;
        this.messages = [];
        this.pendingToken = null;
        this.orderNumber = null;
        this.renderedCount = 0;
        if (this.open) this.render();
        return;
      }
      if (this.open && !this.busy) {
        await this.restore();
        this.render();
        this.scrollToBottom(true);
      } else {
        this.loaded = false; // reload the history next time the chat opens
        if (!this.open) this.unread.hidden = false;
      }
    });
  }

  // ── data ──
  async restore() {
    if (!this.conversationId) return;
    this.restoring = true;
    try {
      const { data } = await api.get(`/conversations/${encodeURIComponent(this.conversationId)}/`);
      this.messages = data.messages || [];
      this.pendingToken = data.pending_token || null;
      this.orderNumber = data.order_number || null;
      this.renderedCount = this.messages.length; // history appears without the entry animation
      this.checkInflight();
    } catch (error) {
      if (error?.response?.status === 404) {
        this.conversationId = null;
        local.set(KEYS.conv, null);
        this.messages = [];
      } else {
        this.error = "Не вдалося завантажити розмову. Перевірте інтернет.";
      }
    } finally {
      this.restoring = false;
    }
  }

  /** A message sent right before the page closed: did its reply arrive? */
  checkInflight() {
    const inflight = local.json(KEYS.inflight);
    if (!inflight || Date.now() - inflight.ts > 30 * 60 * 1000) {
      local.set(KEYS.inflight, null);
      return;
    }
    if (inflight.conv && inflight.conv !== this.conversationId) return;
    const users = this.messages.filter((m) => m.role === "user");
    const last = users[users.length - 1];
    const answered = last && last.content === inflight.text && this.messages[this.messages.length - 1].role !== "user";
    if (answered) {
      local.set(KEYS.inflight, null);
      this.recovery = null;
    } else if (!this.busy) {
      this.recovery = inflight;
    }
  }

  async loadCategories() {
    if (this.categories) return this.categories;
    try {
      const { data } = await api.get("/config/");
      this.categories = data.categories || [];
    } catch (e) {
      this.categories = [];
    }
    return this.categories;
  }

  async send(raw, opts = {}) {
    const text = String(raw || "").trim().slice(0, LIMIT);
    if (!text || this.busy || Date.now() < this.cooldownUntil) return;
    this.busy = true;
    this.error = null;
    this.recovery = null;
    if (text === PICK_RUG) this.openPicker();
    else if (!opts.keepPicker) this.closePicker();
    this.messages.push({ id: `local-${Date.now()}`, role: "user", content: text });
    // A tapped chip or tile keeps whatever the buyer was typing.
    if (opts.fromInput) {
      this.input.value = "";
      local.set(KEYS.draft, null);
      this.autosize();
    }
    local.set(KEYS.inflight, JSON.stringify({ text, conv: this.conversationId, ts: Date.now() }));
    this.render();
    this.scrollToBottom(true);
    this.startThinking();
    trackEvent("assistant_message", { page_type: window.__mrPageType || "" });

    try {
      const { data } = await api.post("/message/", {
        message: text,
        page: { path: window.location.pathname },
        ...(this.conversationId ? { conversation_id: this.conversationId } : {}),
      });
      this.conversationId = data.conversation_id;
      local.set(KEYS.conv, data.conversation_id);
      local.set(KEYS.inflight, null);
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
      this.broadcast();
    } catch (error) {
      const status = error?.response?.status;
      const retry = Number(error?.response?.headers?.["retry-after"]) || 0;
      if (status === 429 && retry) {
        this.cooldownUntil = Date.now() + retry * 1000;
        setTimeout(() => this.syncSend(), retry * 1000 + 50);
      }
      if (status) local.set(KEYS.inflight, null); // the server answered: nothing to recover
      this.error =
        error?.response?.data?.error ||
        (navigator.onLine === false
          ? "Немає інтернету. Перевірте з'єднання і спробуйте ще раз."
          : "Не вдалося надіслати. Спробуйте ще раз або подзвоніть нам: +380 96 398 88 75.");
      // Give the text back so nothing typed is lost.
      const last = this.messages[this.messages.length - 1];
      if (last && last.role === "user" && String(last.id).startsWith("local-")) {
        this.messages.pop();
        this.renderedCount = Math.min(this.renderedCount, this.messages.length);
        if (!this.input.value.trim()) {
          this.input.value = text;
          local.set(KEYS.draft, text);
          this.autosize();
        }
      }
    } finally {
      this.busy = false;
      this.stopThinking();
      this.render();
      this.scrollToBottom(true);
      if (!isPhone() && this.open) this.input.focus({ preventScroll: true });
    }
  }

  startThinking() {
    let i = 0;
    this.thinkingText = THINKING[0];
    clearInterval(this.thinkingTimer);
    this.thinkingTimer = setInterval(() => {
      i = (i + 1) % THINKING.length;
      this.thinkingText = THINKING[i];
      const label = this.log.querySelector(".assistant-typing-label");
      if (label) {
        label.classList.remove("is-swap");
        void label.offsetWidth;
        label.textContent = this.thinkingText;
        label.classList.add("is-swap");
      }
    }, 2600);
  }

  stopThinking() {
    clearInterval(this.thinkingTimer);
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

  reset() {
    if (this.busy) return;
    this.conversationId = null;
    local.set(KEYS.conv, null);
    local.set(KEYS.inflight, null);
    this.messages = [];
    this.pendingToken = null;
    this.orderNumber = null;
    this.error = null;
    this.recovery = null;
    this.renderedCount = 0;
    this.closePicker();
    this.broadcast();
    this.render();
    this.input.focus({ preventScroll: true });
  }

  // ── clicks ──
  onClick(event) {
    const t = event.target;
    const pick = t.closest("[data-send]");
    if (pick) {
      this.send(pick.dataset.send, { keepPicker: pick.dataset.keepPicker === "1" });
      return;
    }
    if (t.closest("[data-picker-close]")) {
      this.closePicker();
      return;
    }
    const confirmBtn = t.closest("[data-order-confirm]");
    if (confirmBtn) {
      this.confirmOrder(confirmBtn);
      return;
    }
    if (t.closest("[data-order-edit]")) {
      this.input.value = "Хочу змінити в замовленні: ";
      this.autosize();
      this.syncSend();
      this.input.focus();
      return;
    }
    const sizeBtn = t.closest("[data-add-size]");
    if (sizeBtn) {
      this.send(`Додай у кошик ${sizeBtn.dataset.title}, розмір ${sizeBtn.dataset.size}`);
      return;
    }
    if (t.closest("[data-recover-send]") && this.recovery) {
      const text = this.recovery.text;
      local.set(KEYS.inflight, null);
      this.recovery = null;
      this.send(text);
      return;
    }
    if (t.closest("[data-recover-drop]")) {
      local.set(KEYS.inflight, null);
      this.recovery = null;
      this.render();
    }
  }

  async openPicker() {
    this.picker = "categories";
    this.renderPicker();
    await this.loadCategories();
    if (this.picker !== "categories") return;
    if (!this.categories.length) this.closePicker();
    else this.renderPicker();
  }

  closePicker() {
    if (!this.picker) return;
    this.picker = null;
    this.renderPicker();
  }

  async confirmOrder(button) {
    const card = button.closest(".assistant-order");
    const order = this.findOrder(button.dataset.orderConfirm);
    if (!order || this.busy) return;
    this.busy = true;
    button.disabled = true;
    button.classList.add("is-loading");
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
        const placed = await api.post(`/conversations/${encodeURIComponent(this.conversationId)}/order-placed/`, {
          token: order.token,
          order_number: number,
        });
        if (placed.data?.message) this.messages.push(placed.data.message);
      } catch (e) {
        /* the order exists; the chat note is a nicety */
      }
      this.pendingToken = null;
      this.orderNumber = number;
      this.busy = false;
      this.render();
      this.scrollToBottom(true);
      this.broadcast();
      updateCountBadge(".header_bottom_panel_cart", 0);
      const redirect = data?.redirect_url || (order.payment_type === "liqpay" ? "/payment/" : "/success/");
      setTimeout(() => {
        window.location.href = redirect;
      }, 2200);
    } catch (error) {
      this.busy = false;
      button.disabled = false;
      button.classList.remove("is-loading");
      button.textContent = "Підтвердити замовлення";
      const data = error?.response?.data || {};
      const firstField = Object.keys(data).find((k) => Array.isArray(data[k]));
      errorBox.textContent =
        data.message ||
        data.error ||
        (firstField ? `${firstField}: ${data[firstField][0]}` : "") ||
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

  // ── layout helpers ──
  autosize() {
    this.input.style.height = "auto";
    const h = Math.min(this.input.scrollHeight, 132);
    this.input.style.height = `${h}px`;
    this.input.classList.toggle("is-scrolling", this.input.scrollHeight > 132);
  }

  syncSend() {
    this.sendBtn.disabled = this.busy || !this.input.value.trim() || Date.now() < this.cooldownUntil;
  }

  nearBottom() {
    return this.log.scrollHeight - this.log.scrollTop - this.log.clientHeight < 80;
  }

  scrollToBottom(smooth) {
    requestAnimationFrame(() => {
      this.log.scrollTo({ top: this.log.scrollHeight, behavior: smooth && !reduceMotion() ? "smooth" : "auto" });
      this.latestBtn.hidden = true;
    });
  }

  // ── rendering ──
  render() {
    const wasNearBottom = this.nearBottom();
    this.log.textContent = "";
    if (!this.messages.length && !this.restoring) this.log.appendChild(this.renderWelcome());
    if (this.restoring && !this.messages.length) this.log.appendChild(this.renderSkeleton());
    const lastQuickIndex = this.lastQuickIndex();
    this.messages.forEach((message, index) => {
      const node = this.renderMessage(message, index === lastQuickIndex && !this.busy);
      if (index >= this.renderedCount) node.classList.add("is-new");
      this.log.appendChild(node);
    });
    this.renderedCount = this.messages.length;
    if (this.busy) this.log.appendChild(this.renderTyping());
    if (this.recovery && !this.busy) this.log.appendChild(this.renderRecovery());
    if (this.error) {
      const box = el("div", "assistant-error is-new", this.error);
      box.setAttribute("role", "alert");
      this.log.appendChild(box);
    }
    this.input.disabled = false;
    this.syncSend();
    if (!wasNearBottom && this.messages.length) this.latestBtn.hidden = false;
  }

  lastQuickIndex() {
    const last = this.messages.length - 1;
    if (last < 0) return -1;
    const m = this.messages[last];
    return m.role !== "user" && m.quick_replies && m.quick_replies.length ? last : -1;
  }

  renderWelcome() {
    const box = el("div", "assistant-welcome is-new");
    box.innerHTML = `<div class="assistant-welcome-art" aria-hidden="true">${ICONS.rug}</div>`;
    box.appendChild(el("p", "assistant-welcome-title", "Привіт! Я допоможу обрати килим"));
    box.appendChild(
      el("p", "assistant-welcome-text", "Розкажіть про кімнату, розмір чи колір. Підкажу про доставку і можу оформити замовлення прямо тут.")
    );
    const list = el("div", "assistant-suggestions");
    SUGGESTIONS.forEach((s, i) => {
      const btn = el("button", "assistant-suggestion");
      btn.type = "button";
      btn.dataset.send = s.text;
      btn.style.setProperty("--i", i);
      btn.innerHTML = `<span class="assistant-suggestion-icon">${ICONS[s.icon]}</span><span>${escapeHtml(s.text)}</span><span class="assistant-suggestion-arrow">${ICONS.right}</span>`;
      list.appendChild(btn);
    });
    box.appendChild(list);
    return box;
  }

  renderSkeleton() {
    const box = el("div", "assistant-skeleton-wrap");
    box.innerHTML = '<span class="assistant-skeleton is-short"></span><span class="assistant-skeleton"></span><span class="assistant-skeleton is-reply"></span>';
    return box;
  }

  renderTyping() {
    const box = el("div", "assistant-message assistant-message--assistant is-new");
    box.setAttribute("role", "status");
    box.innerHTML = `<div class="assistant-bubble assistant-typing-bubble"><span class="assistant-typing" aria-hidden="true"><i></i><i></i><i></i></span><span class="assistant-typing-label">${escapeHtml(this.thinkingText || THINKING[0])}</span></div>`;
    return box;
  }

  renderRecovery() {
    const box = el("div", "assistant-recovery is-new");
    box.appendChild(el("p", "", `Відповідь на «${this.recovery.text.slice(0, 80)}» не встигла прийти.`));
    const actions = el("div", "assistant-recovery-actions");
    const again = el("button", "assistant-chip is-accent", "Надіслати ще раз");
    again.type = "button";
    again.dataset.recoverSend = "1";
    const drop = el("button", "assistant-chip", "Не треба");
    drop.type = "button";
    drop.dataset.recoverDrop = "1";
    actions.append(again, drop);
    box.appendChild(actions);
    return box;
  }

  renderMessage(message, withQuick) {
    const isUser = message.role === "user";
    const wrap = el("div", `assistant-message assistant-message--${isUser ? "user" : "assistant"}`);
    const bubble = el("div", "assistant-bubble");
    if (isUser) bubble.textContent = message.content;
    else bubble.innerHTML = renderMarkdown(message.content);
    wrap.appendChild(bubble);
    if (message.products && message.products.length) wrap.appendChild(this.renderProducts(message.products));
    if (message.order) wrap.appendChild(this.renderOrder(message.order));
    if (withQuick) {
      const chips = message.quick_replies.map((text, i) => {
        const chip = el("button", "assistant-chip", text);
        chip.type = "button";
        chip.dataset.send = text;
        chip.style.setProperty("--i", i);
        return chip;
      });
      wrap.appendChild(makeSlider("assistant-quick", chips));
    }
    return wrap;
  }

  renderProducts(products) {
    const cards = products.map((p, i) => {
      const soldOut = !(p.sizes && p.sizes.length) && p.sold_out && p.sold_out.length;
      const card = el("article", `assistant-product${soldOut ? " is-sold-out" : ""}`);
      card.style.setProperty("--i", i);
      const link = el("a", "assistant-product-link");
      link.href = p.url;
      const img = rugImage(p.image, p.title, "assistant-product-img");
      if (soldOut) img.appendChild(el("span", "assistant-product-badge", "Немає в наявності"));
      link.appendChild(img);
      const info = el("span", "assistant-product-info");
      info.appendChild(el("span", "assistant-product-title", p.title));
      if (p.price_from) info.appendChild(el("span", "assistant-product-price", `від ${money(p.price_from)}`));
      link.appendChild(info);
      card.appendChild(link);
      if (p.sizes && p.sizes.length) {
        const sizes = el("div", "assistant-product-sizes");
        p.sizes.slice(0, 4).forEach((s) => {
          const btn = el("button", "assistant-size");
          btn.type = "button";
          btn.title = `Додати в кошик: ${s.size}, ${money(s.price)}`;
          btn.dataset.addSize = s.size_id;
          btn.dataset.size = s.size;
          btn.dataset.title = p.title;
          btn.innerHTML = `${ICONS.plus}<span>${escapeHtml(s.size)}</span>`;
          sizes.appendChild(btn);
        });
        card.appendChild(sizes);
      }
      if (soldOut) {
        const sizes = el("div", "assistant-product-sizes");
        p.sold_out.slice(0, 3).forEach((s) => {
          const btn = el("button", "assistant-size is-request", `Заявка ${s.size}`);
          btn.type = "button";
          btn.title = "Залишити заявку: менеджер зателефонує, коли привезуть";
          btn.dataset.send = `Хочу залишити заявку на ${p.title}, розмір ${s.size}, його зараз немає`;
          sizes.appendChild(btn);
        });
        card.appendChild(sizes);
      }
      return card;
    });
    return makeSlider("assistant-products", cards);
  }

  renderOrder(order) {
    const active = order.token && order.token === this.pendingToken;
    const lastOrder = [...this.messages].reverse().find((m) => m.order)?.order;
    const placed = !active && this.orderNumber && lastOrder === order;
    const card = el("div", `assistant-order${active ? "" : " is-stale"}${placed ? " is-placed" : ""}`);
    const head = el("div", "assistant-order-head");
    head.innerHTML = `<span class="assistant-order-icon">${placed ? ICONS.check : ICONS.bag}</span>`;
    head.appendChild(el("p", "assistant-order-title", placed ? `Замовлення №${this.orderNumber} оформлено` : "Перевірте замовлення"));
    card.appendChild(head);
    const list = el("ul", "assistant-order-items");
    (order.items || []).forEach((item) => {
      const li = el("li");
      li.appendChild(el("span", "", `${item.title}, ${item.size}${item.quantity > 1 ? ` × ${item.quantity}` : ""}`));
      li.appendChild(el("strong", "", money(item.line_total)));
      list.appendChild(li);
    });
    card.appendChild(list);
    const rows = [
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
    const total = el("div", "assistant-order-total");
    total.appendChild(el("span", "", "Разом"));
    total.appendChild(el("strong", "", money(order.total)));
    card.appendChild(total);
    const error = el("p", "assistant-order-error");
    error.setAttribute("role", "alert");
    card.appendChild(error);
    if (active) {
      const actions = el("div", "assistant-order-actions");
      const ok = el("button", "assistant-order-confirm", "Підтвердити замовлення");
      ok.type = "button";
      ok.dataset.orderConfirm = order.token;
      const edit = el("button", "assistant-order-edit", "Змінити");
      edit.type = "button";
      edit.dataset.orderEdit = "1";
      actions.append(ok, edit);
      card.appendChild(actions);
    } else if (!placed) {
      card.appendChild(el("p", "assistant-order-stale", "Ця картка вже не активна"));
    }
    return card;
  }

  renderPicker() {
    const box = this.pickerBox;
    box.textContent = "";
    if (this.picker !== "categories") {
      box.classList.remove("is-visible");
      box.hidden = true;
      return;
    }
    box.hidden = false;
    requestAnimationFrame(() => box.classList.add("is-visible"));
    const head = el("div", "assistant-picker-head");
    head.appendChild(el("span", "", "Оберіть, де лежатиме килим"));
    const close = el("button", "assistant-picker-close");
    close.type = "button";
    close.dataset.pickerClose = "1";
    close.setAttribute("aria-label", "Сховати категорії");
    close.innerHTML = ICONS.close;
    head.appendChild(close);
    box.appendChild(head);
    if (!this.categories) {
      const loading = [0, 1, 2, 3].map(() => el("span", "assistant-tile is-skeleton"));
      box.appendChild(makeSlider("assistant-tiles", loading));
      return;
    }
    const tiles = this.categories.map((c, i) => {
      const tile = el("button", "assistant-tile");
      tile.type = "button";
      tile.dataset.send = `Покажи килими з категорії «${c.title}»`;
      tile.style.setProperty("--i", i);
      tile.appendChild(rugImage(c.image, "", "assistant-tile-img"));
      tile.appendChild(el("span", "assistant-tile-label", c.title));
      return tile;
    });
    box.appendChild(makeSlider("assistant-tiles", tiles));
  }
}

function boot() {
  if (window.__mrcAssistant) return;
  window.__mrcAssistant = new AssistantWidget();
}

if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
else boot();
