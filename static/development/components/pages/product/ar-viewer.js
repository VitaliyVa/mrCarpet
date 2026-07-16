/**
 * Product 3D / AR modal — lazy-loads model-viewer only on open.
 */
const MODEL_VIEWER_SRC =
  "https://unpkg.com/@google/model-viewer@4.0.0/dist/model-viewer.min.js";

const FLOOR_BASE = "/static/ar/floors/";
/**
 * Floor extent (code switch, not UI):
 * - "single" — one cover image under the rug
 * - "tiled"  — center + 1 tile each side (3×3 repeat)
 */
const FLOOR_EXTENT_MODE = "single";
const FLOOR_PRESETS = [
  { id: "white", label: "Білий", src: null },
  { id: "oak-light", label: "Світлий дуб", src: FLOOR_BASE + "oak-light.webp" },
  { id: "oak-natural", label: "Натуральний дуб", src: FLOOR_BASE + "oak-natural.webp" },
  { id: "oak-bleached", label: "Вибілений дуб", src: FLOOR_BASE + "oak-bleached.webp" },
  { id: "oak-grey", label: "Сірий дуб", src: FLOOR_BASE + "oak-grey.webp" },
  { id: "ash-light", label: "Світлий ясен", src: FLOOR_BASE + "ash-light.webp" },
  { id: "laminate-beige", label: "Бежевий ламінат", src: FLOOR_BASE + "laminate-beige.webp" },
  { id: "herringbone", label: "Ялинка", src: FLOOR_BASE + "herringbone.webp?v=3" },
  { id: "walnut-dark", label: "Горіх", src: FLOOR_BASE + "walnut-dark.webp" },
  { id: "wenge", label: "Венге", src: FLOOR_BASE + "wenge.webp" },
  { id: "marble-white", label: "Мармур", src: FLOOR_BASE + "marble-white.webp" },
  { id: "tile-cream", label: "Кремова плитка", src: FLOOR_BASE + "tile-cream.webp" },
  { id: "concrete", label: "Бетон", src: FLOOR_BASE + "concrete.webp" },
];

let mvScriptPromise = null;
let modelViewerEl = null;
let currentSizeLabel = null;
let autoArRequested = false;
let currentFloorId = "white";
let customFloorObjectUrl = null;
let targetYaw = 0;
let targetPitch = 0;
let targetScale = 1;
let displayYaw = 0;
let displayPitch = 0;
let displayScale = 1;
let scenePointerBound = false;
let sceneVelYaw = 0;
let sceneVelPitch = 0;
let sceneLoopRaf = 0;
let sceneDragging = false;
const DEFAULT_CAMERA_ORBIT = "0deg 0deg 150%";
const DEFAULT_FOV = 32;
const SCENE_PITCH_MAX = 86;
const SCENE_SCALE_MIN = 0.55;
const SCENE_SCALE_MAX = 2.4;
const SCENE_YAW_SENS = 0.38;
const SCENE_PITCH_SENS = 0.32;
const SCENE_FRICTION = 0.965;
const SCENE_VEL_MIN = 0.015;
const SCENE_LERP = 0.1;

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

function clampScenePitch(value) {
  return Math.max(-SCENE_PITCH_MAX, Math.min(SCENE_PITCH_MAX, value));
}

function applySceneTransform() {
  const scene = document.getElementById("product-ar-scene");
  if (!scene) return;
  scene.style.transform =
    `rotateX(${displayPitch}deg) rotateZ(${displayYaw}deg) scale(${displayScale})`;
}

function stopSceneLoop() {
  sceneVelYaw = 0;
  sceneVelPitch = 0;
  sceneDragging = false;
  if (sceneLoopRaf) {
    cancelAnimationFrame(sceneLoopRaf);
    sceneLoopRaf = 0;
  }
}

function ensureSceneLoop() {
  if (sceneLoopRaf) return;

  const tick = () => {
    if (!sceneDragging) {
      if (Math.abs(sceneVelYaw) > SCENE_VEL_MIN) {
        targetYaw += sceneVelYaw;
        sceneVelYaw *= SCENE_FRICTION;
      } else {
        sceneVelYaw = 0;
      }
      if (Math.abs(sceneVelPitch) > SCENE_VEL_MIN) {
        targetPitch = clampScenePitch(targetPitch + sceneVelPitch);
        sceneVelPitch *= SCENE_FRICTION;
      } else {
        sceneVelPitch = 0;
      }
    }

    displayYaw += (targetYaw - displayYaw) * SCENE_LERP;
    displayPitch += (targetPitch - displayPitch) * SCENE_LERP;
    displayScale += (targetScale - displayScale) * SCENE_LERP;

    if (Math.abs(targetYaw - displayYaw) < 0.01) displayYaw = targetYaw;
    if (Math.abs(targetPitch - displayPitch) < 0.01) displayPitch = targetPitch;
    if (Math.abs(targetScale - displayScale) < 0.001) displayScale = targetScale;

    applySceneTransform();
    sceneLoopRaf = requestAnimationFrame(tick);
  };

  sceneLoopRaf = requestAnimationFrame(tick);
}

function resetSceneTransform() {
  sceneVelYaw = 0;
  sceneVelPitch = 0;
  sceneDragging = false;
  targetYaw = 0;
  targetPitch = 0;
  targetScale = 1;
  displayYaw = 0;
  displayPitch = 0;
  displayScale = 1;
  applySceneTransform();
}

function resetViewerCamera() {
  const mv = modelViewerEl || document.querySelector(".product-ar-modal__mv");
  if (!mv) return;

  const prevDecay = mv.interpolationDecay;
  if (typeof prevDecay === "number") mv.interpolationDecay = 0;

  mv.setAttribute("camera-orbit", DEFAULT_CAMERA_ORBIT);
  mv.setAttribute("field-of-view", `${DEFAULT_FOV}deg`);
  if ("cameraOrbit" in mv) mv.cameraOrbit = DEFAULT_CAMERA_ORBIT;
  if ("fieldOfView" in mv) mv.fieldOfView = `${DEFAULT_FOV}deg`;

  if (typeof prevDecay === "number") {
    requestAnimationFrame(() => {
      mv.interpolationDecay = prevDecay;
    });
  }
}

function bindSceneControls() {
  const hit = document.getElementById("product-ar-scene-hit");
  if (!hit || scenePointerBound) return;
  scenePointerBound = true;
  ensureSceneLoop();

  let lastX = 0;
  let lastY = 0;
  let lastTs = 0;
  let pinchStartDist = 0;
  let pinchStartScale = 1;

  const onPointerDown = (e) => {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    sceneDragging = true;
    sceneVelYaw = 0;
    sceneVelPitch = 0;
    lastX = e.clientX;
    lastY = e.clientY;
    lastTs = performance.now();
    hit.setPointerCapture?.(e.pointerId);
  };

  const onPointerMove = (e) => {
    if (!sceneDragging) return;
    const now = performance.now();
    const dt = Math.max(8, Math.min(40, now - lastTs || 16));
    const dx = e.clientX - lastX;
    const dy = e.clientY - lastY;
    lastX = e.clientX;
    lastY = e.clientY;
    lastTs = now;

    // Invert only yaw. Pitch up/down unchanged.
    const dYaw = -dx * SCENE_YAW_SENS;
    const dPitch = -dy * SCENE_PITCH_SENS;
    targetYaw += dYaw;
    targetPitch = clampScenePitch(targetPitch + dPitch);

    const frameScale = 16 / dt;
    sceneVelYaw = dYaw * frameScale;
    sceneVelPitch = dPitch * frameScale;
  };

  const onPointerUp = (e) => {
    if (!sceneDragging) return;
    sceneDragging = false;
    try {
      hit.releasePointerCapture?.(e.pointerId);
    } catch (_) {
      /* ignore */
    }
  };

  hit.addEventListener("pointerdown", onPointerDown);
  hit.addEventListener("pointermove", onPointerMove);
  hit.addEventListener("pointerup", onPointerUp);
  hit.addEventListener("pointercancel", onPointerUp);
  hit.addEventListener(
    "wheel",
    (e) => {
      e.preventDefault();
      const next = targetScale * (e.deltaY > 0 ? 0.97 : 1.03);
      targetScale = Math.max(SCENE_SCALE_MIN, Math.min(SCENE_SCALE_MAX, next));
    },
    { passive: false }
  );

  hit.addEventListener(
    "touchstart",
    (e) => {
      if (e.touches.length === 2) {
        sceneDragging = false;
        sceneVelYaw = 0;
        sceneVelPitch = 0;
        const a = e.touches[0];
        const b = e.touches[1];
        pinchStartDist = Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
        pinchStartScale = targetScale;
      }
    },
    { passive: true }
  );

  hit.addEventListener(
    "touchmove",
    (e) => {
      if (e.touches.length !== 2 || !pinchStartDist) return;
      e.preventDefault();
      const a = e.touches[0];
      const b = e.touches[1];
      const dist = Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY);
      const next = pinchStartScale * (dist / pinchStartDist);
      targetScale = Math.max(SCENE_SCALE_MIN, Math.min(SCENE_SCALE_MAX, next));
    },
    { passive: false }
  );

  hit.addEventListener(
    "touchend",
    (e) => {
      if (e.touches.length < 2) pinchStartDist = 0;
    },
    { passive: true }
  );
}

function cycleFloor(direction) {
  const ids = FLOOR_PRESETS.map((f) => f.id);
  let idx = ids.indexOf(currentFloorId);
  if (idx < 0) idx = 0;
  idx = (idx + direction + ids.length) % ids.length;
  if (customFloorObjectUrl) {
    URL.revokeObjectURL(customFloorObjectUrl);
    customFloorObjectUrl = null;
  }
  applyFloor(ids[idx]);
}

function bindFloorNav() {
  const prev = document.getElementById("product-ar-floor-prev");
  const next = document.getElementById("product-ar-floor-next");
  if (prev && prev.dataset.bound !== "1") {
    prev.dataset.bound = "1";
    prev.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      cycleFloor(-1);
    });
  }
  if (next && next.dataset.bound !== "1") {
    next.dataset.bound = "1";
    next.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      cycleFloor(1);
    });
  }
}

function applyFloorExtentMode() {
  const floorEl = document.getElementById("product-ar-floor");
  if (!floorEl) return;
  floorEl.dataset.floorExtent =
    FLOOR_EXTENT_MODE === "tiled" ? "tiled" : "single";
}

function applyFloor(floorId, customSrc) {
  const wrap = document.querySelector(".product-ar-modal__viewer-wrap");
  const floorEl = document.getElementById("product-ar-floor");
  const floorTex = document.getElementById("product-ar-floor-tex");
  const mv = modelViewerEl || document.querySelector(".product-ar-modal__mv");
  if (!wrap || !floorEl || !floorTex) return;

  applyFloorExtentMode();

  currentFloorId = floorId || "white";
  const preset = FLOOR_PRESETS.find((f) => f.id === currentFloorId);
  const src =
    customSrc ||
    (currentFloorId === "custom" ? customFloorObjectUrl : preset?.src) ||
    null;

  // Reset shared scene transform + locked top-down camera
  resetSceneTransform();
  resetViewerCamera();

  if (src) {
    floorTex.style.backgroundImage = `url("${src}")`;
    wrap.classList.add("has-floor");
    if (mv) {
      mv.style.background = "transparent";
      mv.style.setProperty("--poster-color", "transparent");
    }
  } else {
    floorTex.style.backgroundImage = "";
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

function positionFloorTooltip(anchor, tooltip) {
  tooltip.style.display = "block";
  tooltip.style.visibility = "hidden";
  tooltip.style.left = "-9999px";
  tooltip.style.top = "0";

  const tooltipHeight = tooltip.offsetHeight;
  const tooltipWidth = tooltip.offsetWidth;
  const rect = anchor.getBoundingClientRect();
  const gap = 8;
  const margin = 12;

  let top = rect.top - tooltipHeight - gap;
  let left = rect.left + rect.width / 2 - tooltipWidth / 2;

  if (top < margin) {
    top = rect.bottom + gap;
    tooltip.classList.add("is-below");
  } else {
    tooltip.classList.remove("is-below");
  }

  if (left + tooltipWidth > window.innerWidth - margin) {
    left = window.innerWidth - tooltipWidth - margin;
  }
  if (left < margin) left = margin;

  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
  tooltip.style.visibility = "";
}

function bindFloorTooltip(anchor, label) {
  if (!anchor || anchor.dataset.tooltipBound === "1") return;
  anchor.dataset.tooltipBound = "1";

  const tooltip = document.createElement("span");
  tooltip.className = "product-ar-modal__floor-tooltip";
  tooltip.setAttribute("role", "tooltip");
  tooltip.textContent = label;
  // Above modal (z-index 10050); body so fixed coords stay viewport-relative
  document.body.appendChild(tooltip);

  let hideTimer = 0;

  const show = () => {
    clearTimeout(hideTimer);
    positionFloorTooltip(anchor, tooltip);
    tooltip.classList.add("is-visible");
  };
  const hide = () => {
    clearTimeout(hideTimer);
    hideTimer = window.setTimeout(() => {
      tooltip.classList.remove("is-visible");
    }, 120);
  };

  // Always bind hover — modal is desktop-first; matchMedia alone was flaky
  anchor.addEventListener("mouseenter", show);
  anchor.addEventListener("mouseleave", hide);
  tooltip.addEventListener("mouseenter", () => clearTimeout(hideTimer));
  tooltip.addEventListener("mouseleave", hide);

  anchor.addEventListener("focus", show);
  anchor.addEventListener("blur", () => {
    clearTimeout(hideTimer);
    tooltip.classList.remove("is-visible");
  });
}

/** CSS floor is preview-only — never part of the GLB / AR session. */
function setPreviewFloorHidden(hidden) {
  const wrap = document.querySelector(".product-ar-modal__viewer-wrap");
  const floorEl = document.getElementById("product-ar-floor");
  const floorsUi = document.getElementById("product-ar-floors");
  const mv = modelViewerEl || document.querySelector(".product-ar-modal__mv");
  if (!wrap || !floorEl) return;

  if (hidden) {
    wrap.classList.remove("has-floor");
    floorEl.hidden = true;
    floorEl.setAttribute("aria-hidden", "true");
    if (floorsUi) floorsUi.style.visibility = "hidden";
    if (mv) {
      mv.style.background = "";
      mv.style.setProperty("--poster-color", "#ffffff");
    }
  } else {
    floorEl.hidden = false;
    if (floorsUi) floorsUi.style.visibility = "";
    applyFloor(currentFloorId);
  }
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
    bindFloorTooltip(btn, floor.label);
  });
}

function bindFloorUpload() {
  const input = document.getElementById("product-ar-floor-upload");
  if (!input || input.dataset.bound === "1") return;
  input.dataset.bound = "1";

  const uploadLabel = input.closest(".product-ar-modal__floor-upload");
  if (uploadLabel) {
    uploadLabel.removeAttribute("title");
    bindFloorTooltip(uploadLabel, "Завантажити свою підлогу");
  }

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
    // No camera-controls: orbit/zoom handled by shared CSS scene (rug + floor)
    modelViewerEl.setAttribute("disable-zoom", "");
    modelViewerEl.setAttribute("shadow-intensity", "0.35");
    modelViewerEl.setAttribute("exposure", "1.05");
    modelViewerEl.setAttribute("interaction-prompt", "none");
    modelViewerEl.setAttribute("camera-orbit", DEFAULT_CAMERA_ORBIT);
    modelViewerEl.setAttribute("field-of-view", `${DEFAULT_FOV}deg`);
    modelViewerEl.setAttribute("min-camera-orbit", "0deg 0deg 150%");
    modelViewerEl.setAttribute("max-camera-orbit", "0deg 0deg 150%");
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
      const status = e.detail?.status;
      // AR shows only the GLB rug — strip CSS floor for the whole session
      if (status === "session-started" || status === "object-placed") {
        setPreviewFloorHidden(true);
      } else if (status === "not-presenting" || status === "failed") {
        setPreviewFloorHidden(false);
      }
      if (status === "failed") {
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
    // Ensure AR / Scene Viewer / Quick Look get rug-only (no CSS floor)
    setPreviewFloorHidden(true);
    try {
      await mv.activateAR();
    } catch (err) {
      setPreviewFloorHidden(false);
      setStatus("Не вдалося відкрити AR на цьому пристрої.", true);
      showQr(currentSizeLabel);
    }
    return;
  }

  // Desktop / no AR support → show QR (preview floor stays)
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
    mv.setAttribute("camera-orbit", DEFAULT_CAMERA_ORBIT);
    mv.setAttribute("field-of-view", `${DEFAULT_FOV}deg`);
    resetSceneTransform();

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
  bindFloorNav();
  bindSceneControls();
  ensureSceneLoop();
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
  stopSceneLoop();
  resetSceneTransform();
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
