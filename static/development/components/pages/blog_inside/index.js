import "./index.scss";
import { trackEvent } from "../../../utils/analytics";

// «Скопіювати посилання»: clipboard API where allowed, a hidden textarea
// otherwise (older Safari, http on a local network).
const copyButton = document.querySelector("[data-share-copy]");
if (copyButton) {
  const box = copyButton.closest("[data-share-url]");
  const url = (box && box.dataset.shareUrl) || window.location.href;
  const label = copyButton.querySelector("[data-share-copy-label]");
  const initial = label ? label.textContent : "";

  const fallbackCopy = () => {
    const area = document.createElement("textarea");
    area.value = url;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    try {
      document.execCommand("copy");
    } catch (e) {
      // nothing else to try
    }
    document.body.removeChild(area);
  };

  copyButton.addEventListener("click", () => {
    const done = () => {
      copyButton.classList.add("is-copied");
      if (label) label.textContent = "Посилання скопійовано";
      setTimeout(() => {
        copyButton.classList.remove("is-copied");
        if (label) label.textContent = initial;
      }, 2200);
    };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(url).then(done, () => {
        fallbackCopy();
        done();
      });
    } else {
      fallbackCopy();
      done();
    }
  });
}

// Side table of contents: highlight the section being read.
const tocLinks = Array.from(document.querySelectorAll("[data-toc-link]"));
if (tocLinks.length && "IntersectionObserver" in window) {
  const byId = new Map(tocLinks.map((link) => [link.dataset.tocLink, link]));
  const headings = Array.from(byId.keys())
    .map((id) => document.getElementById(id))
    .filter(Boolean);

  const setActive = (id) => {
    tocLinks.forEach((link) =>
      link.classList.toggle("is-active", link.dataset.tocLink === id)
    );
  };

  const observer = new IntersectionObserver(
    (entries) => {
      const visible = entries
        .filter((entry) => entry.isIntersecting)
        .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
      if (visible.length) setActive(visible[0].target.id);
    },
    { rootMargin: "0px 0px -65% 0px", threshold: 0 }
  );
  headings.forEach((heading) => observer.observe(heading));
}

// The inline (mobile) contents closes after a jump, so it does not sit
// open above the section the reader just picked.
const inlineToc = document.querySelector(".bl-toc--inline");
if (inlineToc) {
  inlineToc.addEventListener("click", (event) => {
    if (event.target.closest("a")) inlineToc.removeAttribute("open");
  });
}

// ---- Reading analytics --------------------------------------------------
// article_read at 25/50/75/100 % of the article body (not the page: the
// footer and related posts would make every reader look like a finisher),
// with the active reading time so far; toc_click; one article_time on leave.
const articleEl = document.querySelector("[data-article-slug]");
if (articleEl) {
  const slug = articleEl.dataset.articleSlug;
  const body =
    articleEl.querySelector(".bl-article__main") || articleEl;
  const marks = [25, 50, 75, 100];
  const reached = new Set();
  let maxPercent = 0;
  let activeMs = 0;
  let lastTick = Date.now();
  let lastActivity = Date.now();
  const IDLE_MS = 30000;

  // Count time only while the tab is visible and the reader did something
  // in the last 30 s (scroll, key, touch): a tab left open is not reading.
  const tick = () => {
    const now = Date.now();
    if (
      document.visibilityState === "visible" &&
      now - lastActivity < IDLE_MS
    ) {
      activeMs += Math.min(now - lastTick, 5000);
    }
    lastTick = now;
  };
  const seconds = () => Math.round(activeMs / 1000);
  setInterval(tick, 1000);
  ["scroll", "keydown", "pointerdown", "touchstart", "mousemove"].forEach((t) =>
    window.addEventListener(
      t,
      () => {
        lastActivity = Date.now();
      },
      { passive: true }
    )
  );

  const measure = () => {
    const rect = body.getBoundingClientRect();
    const height = rect.height || 1;
    const seen = window.innerHeight - rect.top;
    const percent = Math.max(0, Math.min(100, Math.round((seen / height) * 100)));
    if (percent > maxPercent) maxPercent = percent;
    marks.forEach((mark) => {
      if (percent >= mark && !reached.has(mark)) {
        reached.add(mark);
        tick();
        trackEvent("article_read", {
          article_slug: slug,
          percent_scrolled: mark,
          engagement_time_sec: seconds(),
        });
      }
    });
  };
  let scheduled = false;
  window.addEventListener(
    "scroll",
    () => {
      if (scheduled) return;
      scheduled = true;
      requestAnimationFrame(() => {
        scheduled = false;
        measure();
      });
    },
    { passive: true }
  );
  // A short article can be fully on screen at once.
  window.addEventListener("load", measure, { once: true });

  let timeSent = false;
  const sendTime = () => {
    if (timeSent) return;
    tick();
    if (activeMs < 1000) return;
    timeSent = true;
    trackEvent("article_time", {
      article_slug: slug,
      engagement_time_sec: seconds(),
      max_percent_scrolled: maxPercent,
    });
  };
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") sendTime();
  });
  window.addEventListener("pagehide", sendTime);

  document.addEventListener("click", (event) => {
    const link = event.target.closest(".bl-toc a[href^='#']");
    if (!link) return;
    const toc = link.closest(".bl-toc");
    const links = Array.from(toc.querySelectorAll("a[href^='#']"));
    trackEvent("toc_click", {
      article_slug: slug,
      section_id: (link.getAttribute("href") || "").slice(1, 100),
      toc_position: links.indexOf(link) + 1,
      toc_type: toc.classList.contains("bl-toc--side") ? "side" : "inline",
    });
  });
}
