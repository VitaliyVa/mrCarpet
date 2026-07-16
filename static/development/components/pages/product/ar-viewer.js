/**
 * Product 3D / AR modal — lazy-loads model-viewer only on open.
 * Floor is a Three.js plane in the same scene (orbits with the rug).
 */
const MODEL_VIEWER_SRC =
  "https://unpkg.com/@google/model-viewer@4.3.1/dist/model-viewer.min.js";

const FLOOR_BASE = "/static/ar/floors/";
const FLOOR_SIZE_M = 10;
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
let threePromise = null;
let modelViewerEl = null;
let currentSizeLabel = null;
let autoArRequested = false;
let currentFloorId = "white";
let customFloorObjectUrl = null;
let floorMesh = null;
let arPresenting = false;
let cssFloorFallback = false;

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

function loadThree() {
  if (threePromise) return threePromise;
  // Same THREE instance as model-viewer (via importmap → MV bundle)
  threePromise = import(/* webpackIgnore: true */ "three").then((mod) => {
    if (mod && mod.PlaneGeometry) return mod;
    if (mod && mod.default && mod.default.PlaneGeometry) return mod.default;
    return mod;
  });
  return threePromise;
}

function getMvScene(mv) {
  if (!mv) return null;
  for (const sym of Object.getOwnPropertySymbols(mv)) {
    const val = mv[sym];
    if (val && val.isScene && val.target) return val;
  }
  return null;
}

function queueMvRender(mv) {
  const scene = getMvScene(mv);
  if (scene && typeof scene.queueRender === "function") scene.queueRender();
}

function resolveFloorSrc(floorId, customSrc) {
  const id = floorId || "white";
  const preset = FLOOR_PRESETS.find((f) => f.id === id);
  return (
    customSrc ||
    (id === "custom" ? customFloorObjectUrl : preset?.src) ||
    null
  );
}

function setViewerBackground(mv, hasFloor) {
  const wrap = document.querySelector(".product-ar-modal__viewer-wrap");
  const floorEl = document.getElementById("product-ar-floor");
  if (wrap) wrap.classList.toggle("has-floor", Boolean(hasFloor));
  if (!mv) return;
  if (hasFloor) {
    mv.style.background = "transparent";
    mv.style.setProperty("--poster-color", "transparent");
  } else {
    mv.style.background = "";
    mv.style.setProperty("--poster-color", "#ffffff");
    if (floorEl) floorEl.style.backgroundImage = "";
  }
}

function applyCssFloorFallback(src) {
  const floorEl = document.getElementById("product-ar-floor");
  if (!floorEl) return;
  floorEl.style.backgroundImage = src ? `url("${src}")` : "";
}

async function ensureFloorMesh() {
  const THREE = await loadThree();
  if (floorMesh) return { THREE, mesh: floorMesh };

  const geometry = new THREE.PlaneGeometry(FLOOR_SIZE_M, FLOOR_SIZE_M);
  const material = new THREE.MeshStandardMaterial({
    color: 0xffffff,
    roughness: 0.95,
    metalness: 0,
  });
  floorMesh = new THREE.Mesh(geometry, material);
  floorMesh.name = "product-ar-floor-mesh";
  floorMesh.rotation.x = -Math.PI / 2;
  floorMesh.position.y = 0;
  floorMesh.renderOrder = -1;
  floorMesh.receiveShadow = true;
  floorMesh.userData.noHit = true;
  return { THREE, mesh: floorMesh };
}

async function setFloorTexture(src) {
  const { THREE, mesh } = await ensureFloorMesh();
  const material = mesh.material;
  if (!src) {
    if (material.map) {
      material.map.dispose();
      material.map = null;
    }
    material.needsUpdate = true;
    return;
  }

  const loader = new THREE.TextureLoader();
  const texture = await new Promise((resolve, reject) => {
    loader.load(src, resolve, undefined, reject);
  });
  if ("SRGBColorSpace" in THREE) texture.colorSpace = THREE.SRGBColorSpace;
  else if ("sRGBEncoding" in THREE) texture.encoding = THREE.sRGBEncoding;
  texture.wrapS = THREE.ClampToEdgeWrapping;
  texture.wrapT = THREE.ClampToEdgeWrapping;

  if (material.map) material.map.dispose();
  material.map = texture;
  material.needsUpdate = true;
}

function attachFloorMesh(mv) {
  if (!floorMesh || !mv) return false;
  const scene = getMvScene(mv);
  if (!scene || !scene.target) return false;
  if (floorMesh.parent !== scene.target) {
    scene.target.add(floorMesh);
  }
  // Keep floor out of framing: it is NOT in scene._models, only on target
  floorMesh.visible = currentFloorId !== "white" && !arPresenting;
  queueMvRender(mv);
  return true;
}

function getFloorCycleIds() {
  const ids = FLOOR_PRESETS.map((f) => f.id);
  if (customFloorObjectUrl || currentFloorId === "custom") {
    ids.push("custom");
  }
  return ids;
}

function syncFloorChipActive() {
  document.querySelectorAll(".product-ar-modal__floor-chip").forEach((chip) => {
    const active = chip.dataset.floorId === currentFloorId;
    chip.classList.toggle("is-active", active);
    if (active && typeof chip.scrollIntoView === "function") {
      chip.scrollIntoView({
        behavior: "smooth",
        inline: "center",
        block: "nearest",
      });
    }
  });
}

function cycleFloor(delta) {
  const ids = getFloorCycleIds();
  if (!ids.length) return;
  let idx = ids.indexOf(currentFloorId);
  if (idx < 0) idx = 0;
  const nextId = ids[(idx + delta + ids.length) % ids.length];
  if (nextId === "custom") {
    applyFloor("custom", customFloorObjectUrl);
  } else {
    if (customFloorObjectUrl && currentFloorId === "custom") {
      // keep blob while cycling away; revoke only on close / new upload
    }
    applyFloor(nextId);
  }
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

async function applyFloor(floorId, customSrc) {
  currentFloorId = floorId || "white";
  const src = resolveFloorSrc(currentFloorId, customSrc);
  const mv = modelViewerEl || document.querySelector(".product-ar-modal__mv");

  syncFloorChipActive();

  if (!src) {
    setViewerBackground(mv, false);
    if (floorMesh) {
      floorMesh.visible = false;
      queueMvRender(mv);
    }
    applyCssFloorFallback(null);
    return;
  }

  setViewerBackground(mv, true);

  if (cssFloorFallback) {
    applyCssFloorFallback(src);
    return;
  }

  try {
    await setFloorTexture(src);
    applyCssFloorFallback(null);
    if (mv && !attachFloorMesh(mv)) {
      // Scene not ready yet (before first GLB load) — attach after load
      if (floorMesh) floorMesh.visible = false;
    }
  } catch (err) {
    console.warn("3D floor failed, CSS fallback", err);
    cssFloorFallback = true;
    applyCssFloorFallback(src);
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
      const status = e.detail?.status;
      arPresenting = status === "session-started" || status === "object-placed";
      if (floorMesh) {
        floorMesh.visible =
          currentFloorId !== "white" && !arPresenting && !cssFloorFallback;
        queueMvRender(modelViewerEl);
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

    // Re-attach 3D floor after scene rebuild so it orbits with the rug
    await applyFloor(currentFloorId);

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
    if (modal.hidden) return;
    if (e.key === "Escape") {
      closeModal();
      return;
    }
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      cycleFloor(-1);
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      cycleFloor(1);
    }
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
