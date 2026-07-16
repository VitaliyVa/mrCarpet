/**
 * Product 3D / AR modal — lazy-loads model-viewer only on open.
 */
const MODEL_VIEWER_SRC =
  "https://unpkg.com/@google/model-viewer@4.0.0/dist/model-viewer.min.js";

const FLOOR_BASE = "/static/ar/floors/";
const FLOOR_PRESETS = [
  { id: "white", label: "Білий", src: null },
  { id: "oak-light", label: "Світлий дуб", src: FLOOR_BASE + "oak-light.webp" },
  { id: "oak-grey", label: "Сірий дуб", src: FLOOR_BASE + "oak-grey.webp" },
  { id: "herringbone", label: "Ялинка", src: FLOOR_BASE + "herringbone.webp" },
  { id: "walnut-dark", label: "Горіх", src: FLOOR_BASE + "walnut-dark.webp" },
  { id: "marble-white", label: "Мармур", src: FLOOR_BASE + "marble-white.webp" },
  { id: "concrete", label: "Бетон", src: FLOOR_BASE + "concrete.webp" },
];

let mvScriptPromise = null;
let modelViewerEl = null;
let currentSizeLabel = null;
let autoArRequested = false;
let currentFloorId = "white";
let customFloorObjectUrl = null;

function loadModelViewerScript() {
  if (customElements.get("model-viewer")) {
    return Promise.resolve();
  }
  if (mvScriptPromise) return mvScriptPromise;

  mvScriptPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[src="${MODEL_VIEWER_SRC}"]`);
    if (existing) {
      existing.addEventListener("load", () => resolve());
      existing.addEventListener("error", reject);
      return;
    }
    const script = document.createElement("script");
    script.type = "module";
    script.src = MODEL_VIEWER_SRC;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Не вдалося завантажити model-viewer"));
    document.body.appendChild(script);
    const started = Date.now();
    const poll = setInterval(() => {
      if (customElements.get("model-viewer")) {
        clearInterval(poll);
        resolve();
      } else if (Date.now() - started > 15000) {
        clearInterval(poll);
        reject(new Error("Таймаут завантаження model-viewer"));
      }
    }, 100);
  });

  return mvScriptPromise;
}

function getProductRoot() {
  return document.querySelector(".product[data-ar-ready]");
}

function getActiveSizeLabel() {
  const active = document.querySelector(".sizes-block .size-label.active");
  return active ? active.textContent.trim() : null;
}

function getSizeChips() {
  return [...document.querySelectorAll(".sizes-block .size-label")].map((el) => ({
    label: el.textContent.trim(),
    itemId: el.dataset.item,
    el,
  }));
}

function setPdpActiveSize(label) {
  const chips = document.querySelectorAll(".sizes-block .size-label");
  chips.forEach((chip) => {
    const match = chip.textContent.trim() === label;
    chip.classList.toggle("active", match);
    if (match) {
      chip.dispatchEvent(new Event("click", { bubbles: true }));
    }
  });
}

function buildDeepLink({ size, ar }) {
  const url = new URL(window.location.href);
  url.searchParams.set("view3d", "1");
  if (size) url.searchParams.set("size", size);
  if (ar) url.searchParams.set("ar", "1");
  else url.searchParams.delete("ar");
  return url.toString();
}

function hideQr() {
  const qrWrap = document.getElementById("product-ar-qr");
  if (qrWrap) qrWrap.hidden = true;
}

function showQr(sizeLabel) {
  const qrWrap = document.getElementById("product-ar-qr");
  const qrImg = document.getElementById("product-ar-qr-img");
  if (!qrWrap || !qrImg) return;

  const link = buildDeepLink({ size: sizeLabel || currentSizeLabel, ar: true });
  qrImg.src =
    "https://api.qrserver.com/v1/create-qr-code/?size=120x120&data=" +
    encodeURIComponent(link);
  qrWrap.hidden = false;
}

function setStatus(text, isError) {
  const el = document.getElementById("product-ar-status");
  if (!el) return;
  el.textContent = text || "";
  el.classList.toggle("is-error", Boolean(isError));
}

function setLoading(visible) {
  const el = document.getElementById("product-ar-loading");
  if (el) el.hidden = !visible;
}

async function fetchGlbUrl(sizeLabel) {
  const openBtn = document.getElementById("product-ar-open");
  const root = getProductRoot();
  let endpoint = openBtn?.dataset.arGlbUrl;
  if (!endpoint && root?.dataset.productSlug) {
    endpoint = `/catalog/product/${root.dataset.productSlug}/ar-glb/`;
  }
  if (!endpoint) throw new Error("Немає AR endpoint");

  const url = new URL(endpoint, window.location.origin);
  url.searchParams.set("size", sizeLabel);

  const res = await fetch(url.toString(), { credentials: "same-origin" });
  const data = await res.json();
  if (!res.ok || !data.success) {
    throw new Error(data.error || "Не вдалося отримати GLB");
  }
  return data.glb_url;
}

function applyFloor(floorId, customSrc) {
  const wrap = document.querySelector(".product-ar-modal__viewer-wrap");
  const floorEl = document.getElementById("product-ar-floor");
  const mv = modelViewerEl || document.querySelector(".product-ar-modal__mv");
  if (!wrap || !floorEl) return;

  currentFloorId = floorId || "white";
  const preset = FLOOR_PRESETS.find((f) => f.id === currentFloorId);
  const src =
    customSrc ||
    (currentFloorId === "custom" ? customFloorObjectUrl : preset?.src) ||
    null;

  if (src) {
    floorEl.style.backgroundImage = `url("${src}")`;
    wrap.classList.add("has-floor");
    if (mv) {
      mv.style.background = "transparent";
      mv.style.setProperty("--poster-color", "transparent");
    }
  } else {
    floorEl.style.backgroundImage = "";
    wrap.classList.remove("has-floor");
    if (mv) {
      mv.style.background = "";
      mv.style.setProperty("--poster-color", "#ffffff");
    }
  }

  document.querySelectorAll(".product-ar-modal__floor-chip").forEach((chip) => {
    chip.classList.toggle("is-active", chip.dataset.floorId === currentFloorId);
  });
}

function renderFloorPicker() {
  const list = document.getElementById("product-ar-floors-list");
  if (!list || list.dataset.ready === "1") return;
  list.dataset.ready = "1";
  list.innerHTML = "";

  FLOOR_PRESETS.forEach((floor) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className =
      "product-ar-modal__floor-chip" +
      (floor.id === currentFloorId ? " is-active" : "");
    btn.dataset.floorId = floor.id;
    btn.title = floor.label;
    btn.setAttribute("aria-label", floor.label);
    if (floor.src) {
      btn.style.backgroundImage = `url("${floor.src}")`;
    } else {
      btn.classList.add("is-white");
    }
    btn.addEventListener("click", () => {
      if (customFloorObjectUrl && currentFloorId === "custom") {
        URL.revokeObjectURL(customFloorObjectUrl);
        customFloorObjectUrl = null;
      }
      applyFloor(floor.id);
    });
    list.appendChild(btn);
  });
}

function bindFloorUpload() {
  const input = document.getElementById("product-ar-floor-upload");
  if (!input || input.dataset.bound === "1") return;
  input.dataset.bound = "1";
  input.addEventListener("change", () => {
    const file = input.files && input.files[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setStatus("Оберіть файл зображення для підлоги", true);
      return;
    }
    if (customFloorObjectUrl) URL.revokeObjectURL(customFloorObjectUrl);
    customFloorObjectUrl = URL.createObjectURL(file);
    applyFloor("custom", customFloorObjectUrl);
    input.value = "";
  });
}

function ensureModelViewer() {
  const host = document.getElementById("product-ar-viewer-host");
  if (!host) return null;

  if (!modelViewerEl) {
    modelViewerEl = document.createElement("model-viewer");
    modelViewerEl.setAttribute("alt", "3D килим");
    modelViewerEl.setAttribute("ar", "");
    modelViewerEl.setAttribute("ar-modes", "webxr scene-viewer quick-look");
    modelViewerEl.setAttribute("ar-placement", "floor");
    modelViewerEl.setAttribute("ar-scale", "fixed");
    modelViewerEl.setAttribute("camera-controls", "");
    modelViewerEl.setAttribute("touch-action", "pan-y");
    modelViewerEl.setAttribute("shadow-intensity", "0.35");
    modelViewerEl.setAttribute("exposure", "1.05");
    modelViewerEl.setAttribute("interaction-prompt", "none");
    // Top-down: phi=0 → килим рівно в кадрі (не під нахилом)
    modelViewerEl.setAttribute("camera-orbit", "0deg 0deg 150%");
    modelViewerEl.setAttribute("field-of-view", "32deg");
    modelViewerEl.setAttribute("min-field-of-view", "18deg");
    modelViewerEl.setAttribute("max-field-of-view", "45deg");
    modelViewerEl.setAttribute("max-camera-orbit", "auto 90deg auto");
    modelViewerEl.setAttribute("min-camera-orbit", "auto 0deg auto");
    modelViewerEl.className = "product-ar-modal__mv";

    // Hide built-in AR slot button — we use the sidebar CTA
    const hiddenAr = document.createElement("button");
    hiddenAr.slot = "ar-button";
    hiddenAr.type = "button";
    hiddenAr.setAttribute("aria-hidden", "true");
    hiddenAr.tabIndex = -1;
    hiddenAr.style.display = "none";
    modelViewerEl.appendChild(hiddenAr);

    modelViewerEl.addEventListener("ar-status", (e) => {
      if (e.detail?.status === "failed") {
        setStatus(
          "Не вдалося відкрити AR. Перевірте підтримку пристрою або скористайтесь QR-кодом.",
          true
        );
        showQr(currentSizeLabel);
      }
    });

    host.appendChild(modelViewerEl);
    applyFloor(currentFloorId);
  }
  return modelViewerEl;
}

async function launchAr() {
  hideQr();
  setStatus("");
  const mv = ensureModelViewer();
  if (!mv) return;

  if (mv.canActivateAR) {
    try {
      await mv.activateAR();
    } catch (err) {
      setStatus("Не вдалося відкрити AR на цьому пристрої.", true);
      showQr(currentSizeLabel);
    }
    return;
  }

  // Desktop / no AR support → show QR
  showQr(currentSizeLabel);
}

async function loadSizeIntoViewer(sizeLabel) {
  if (!sizeLabel) {
    setStatus("Оберіть розмір", true);
    return;
  }
  currentSizeLabel = sizeLabel;
  setLoading(true);
  setStatus("");
  hideQr();

  try {
    const glbUrl = await fetchGlbUrl(sizeLabel);
    const mv = ensureModelViewer();
    if (!mv) return;
    mv.src = glbUrl;
    mv.alt = `Килим ${sizeLabel}`;

    await new Promise((resolve) => {
      const onLoad = () => {
        mv.removeEventListener("load", onLoad);
        resolve();
      };
      mv.addEventListener("load", onLoad);
      if (mv.loaded) resolve();
    });

    // Re-frame after load so round rugs aren't clipped
    if (typeof mv.updateFraming === "function") {
      try {
        mv.updateFraming();
      } catch (_) {
        /* ignore */
      }
    }
    mv.setAttribute("camera-orbit", "0deg 0deg 150%");
    mv.setAttribute("field-of-view", "32deg");

    renderModalSizes(sizeLabel);

    if (autoArRequested) {
      autoArRequested = false;
      await launchAr();
    }
  } catch (err) {
    setStatus(err.message || String(err), true);
  } finally {
    setLoading(false);
  }
}

function renderModalSizes(activeLabel) {
  const host = document.getElementById("product-ar-modal-sizes");
  if (!host) return;
  const sizes = getSizeChips();
  host.innerHTML = "";
  sizes.forEach(({ label }) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className =
      "product-ar-modal__size" + (label === activeLabel ? " is-active" : "");
    btn.textContent = label;
    btn.addEventListener("click", () => {
      setPdpActiveSize(label);
    });
    host.appendChild(btn);
  });
}

async function openModal(opts = {}) {
  const modal = document.getElementById("product-ar-modal");
  if (!modal) return;

  modal.hidden = false;
  document.body.classList.add("product-ar-modal-open");
  setLoading(true);
  setStatus("");
  hideQr();
  renderFloorPicker();
  bindFloorUpload();
  applyFloor(currentFloorId);

  try {
    await loadModelViewerScript();
    ensureModelViewer();

    let sizeLabel = opts.size || getActiveSizeLabel();
    if (opts.size) {
      setPdpActiveSize(opts.size);
      sizeLabel = opts.size;
    }
    autoArRequested = Boolean(opts.ar);
    await loadSizeIntoViewer(sizeLabel);
  } catch (err) {
    setStatus(err.message || String(err), true);
    setLoading(false);
  }
}

function closeModal() {
  const modal = document.getElementById("product-ar-modal");
  if (!modal) return;
  modal.hidden = true;
  document.body.classList.remove("product-ar-modal-open");
  autoArRequested = false;
  hideQr();
  if (customFloorObjectUrl) {
    URL.revokeObjectURL(customFloorObjectUrl);
    customFloorObjectUrl = null;
    if (currentFloorId === "custom") {
      currentFloorId = "white";
      applyFloor("white");
    }
  }
}

function handleDeepLink() {
  const params = new URLSearchParams(window.location.search);
  if (params.get("view3d") !== "1") return;

  const guardKey =
    "ar-deeplink:" + window.location.pathname + window.location.search;
  if (sessionStorage.getItem(guardKey)) return;
  sessionStorage.setItem(guardKey, "1");

  const size = params.get("size") || undefined;
  const ar = params.get("ar") === "1";

  setTimeout(() => {
    openModal({ size, ar });
  }, 400);
}

export function initProductArViewer() {
  const root = getProductRoot();
  const openBtn = document.getElementById("product-ar-open");
  const openBtnMobile = document.getElementById("product-ar-open-mobile");
  const modal = document.getElementById("product-ar-modal");
  if (!root || !modal) return;
  if (!openBtn && !openBtnMobile) return;

  const openHandler = (e) => {
    e.preventDefault();
    e.stopPropagation();
    openModal();
  };
  openBtn?.addEventListener("click", openHandler);
  openBtnMobile?.addEventListener("click", openHandler);

  document.querySelectorAll("[data-ar-open-trigger]").forEach((el) => {
    el.addEventListener("click", openHandler);
  });

  document.getElementById("product-ar-launch")?.addEventListener("click", (e) => {
    e.preventDefault();
    launchAr();
  });

  modal.querySelectorAll("[data-ar-close]").forEach((el) => {
    el.addEventListener("click", closeModal);
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !modal.hidden) closeModal();
  });

  document.querySelectorAll(".sizes-block .size-label").forEach((chip) => {
    chip.addEventListener("click", () => {
      if (modal.hidden) return;
      const label = chip.textContent.trim();
      if (label && label !== currentSizeLabel) {
        loadSizeIntoViewer(label);
      }
    });
  });

  handleDeepLink();
}
