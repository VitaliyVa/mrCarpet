/**
 * Product 3D / AR modal — lazy-loads model-viewer only on open.
 * Floor = <extra-model> GLB plane in the same scene (orbits/zooms with the rug).
 */
const MODEL_VIEWER_SRC =
  "https://unpkg.com/@google/model-viewer@4.3.1/dist/model-viewer.min.js";

const FLOOR_BASE = "/static/ar/floors/";
/** Baked size of floor-*.glb planes (metres). */
const FLOOR_SIZE_M = 10;
/** Visual floor span relative to rug so product stays large in frame. */
const FLOOR_TO_RUG = 4.5;
const FLOOR_PRESETS = [
  { id: "white", label: "Білий", thumb: null, glb: null },
  {
    id: "oak-light",
    label: "Світлий дуб",
    thumb: FLOOR_BASE + "oak-light.webp",
    glb: FLOOR_BASE + "oak-light.glb",
  },
  {
    id: "oak-grey",
    label: "Сірий дуб",
    thumb: FLOOR_BASE + "oak-grey.webp",
    glb: FLOOR_BASE + "oak-grey.glb",
  },
  {
    id: "herringbone",
    label: "Ялинка",
    thumb: FLOOR_BASE + "herringbone.webp",
    glb: FLOOR_BASE + "herringbone.glb",
  },
  {
    id: "walnut-dark",
    label: "Горіх",
    thumb: FLOOR_BASE + "walnut-dark.webp",
    glb: FLOOR_BASE + "walnut-dark.glb",
  },
  {
    id: "marble-white",
    label: "Мармур",
    thumb: FLOOR_BASE + "marble-white.webp",
    glb: FLOOR_BASE + "marble-white.glb",
  },
  {
    id: "concrete",
    label: "Бетон",
    thumb: FLOOR_BASE + "concrete.webp",
    glb: FLOOR_BASE + "concrete.glb",
  },
];

let mvScriptPromise = null;
let modelViewerEl = null;
let currentSizeLabel = null;
let autoArRequested = false;
let currentFloorId = "white";
let customFloorGlbUrl = null;
let customFloorThumbUrl = null;
let arPresenting = false;
let floorApplyToken = 0;

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

function getMvScene(mv) {
  if (!mv) return null;
  const seen = new Set();
  let obj = mv;
  while (obj && obj !== HTMLElement.prototype) {
    for (const sym of Object.getOwnPropertySymbols(obj)) {
      if (seen.has(sym)) continue;
      seen.add(sym);
      try {
        const val = mv[sym];
        if (val && val.isScene && val.target) return val;
      } catch (_) {
        /* ignore */
      }
    }
    obj = Object.getPrototypeOf(obj);
  }
  return null;
}

function queueMvRender(mv) {
  const scene = getMvScene(mv);
  if (scene && typeof scene.queueRender === "function") scene.queueRender();
}

function resolveFloorGlb(floorId) {
  const id = floorId || "white";
  if (id === "custom") return customFloorGlbUrl;
  const preset = FLOOR_PRESETS.find((f) => f.id === id);
  return preset?.glb || null;
}

function setViewerChrome(mv, hasFloor) {
  const wrap = document.querySelector(".product-ar-modal__viewer-wrap");
  const floorEl = document.getElementById("product-ar-floor");
  if (wrap) wrap.classList.toggle("has-floor", Boolean(hasFloor));
  if (floorEl) floorEl.style.backgroundImage = "";
  if (!mv) return;
  // Keep white canvas clear; floor is a real 3D mesh under the rug
  mv.style.background = "";
  mv.style.setProperty("--poster-color", "#ffffff");
}

function ensureFloorExtra(mv) {
  let extra = mv.querySelector("extra-model[data-ar-floor]");
  if (!extra) {
    extra = document.createElement("extra-model");
    extra.setAttribute("data-ar-floor", "");
    extra.setAttribute("background", "");
    mv.appendChild(extra);
  }
  return extra;
}

function setFloorModelsVisible(mv, visible) {
  const scene = getMvScene(mv);
  const models = scene?._models || scene?.models;
  if (!models || models.length < 2) return;
  for (let i = 1; i < models.length; i++) {
    models[i].visible = visible;
  }
  queueMvRender(mv);
}

function getRugSizeM(mv) {
  try {
    const dim = typeof mv.getDimensions === "function" ? mv.getDimensions() : null;
    if (dim) return Math.max(Number(dim.x) || 0, Number(dim.z) || 0, 0.25);
  } catch (_) {
    /* ignore */
  }
  return 1;
}

/** Scale floor plane so it sits under the rug (~FLOOR_TO_RUG × rug), not a 10 m arena. */
function syncFloorScaleToRug(mv) {
  const extra = mv?.querySelector?.("extra-model[data-ar-floor]");
  if (!extra) return;
  if (!extra.getAttribute("src")) {
    extra.removeAttribute("scale");
    return;
  }
  const rugM = getRugSizeM(mv);
  const targetFloorM = Math.max(rugM * FLOOR_TO_RUG, rugM + 1.0);
  const s = targetFloorM / FLOOR_SIZE_M;
  extra.setAttribute("scale", `${s} ${s} ${s}`);
}

function waitForMvLoad(mv) {
  return new Promise((resolve) => {
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      mv.removeEventListener("load", finish);
      resolve();
    };
    mv.addEventListener("load", finish);
  });
}

/**
 * Frame camera on the rug only. model-viewer bounds use scene._models,
 * so floor extras must be spliced out before updateFraming (target.remove is not enough).
 */
async function reframedRugOnly(mv) {
  if (!mv) return;
  const scene = getMvScene(mv);
  const orbit = "0deg 0deg 120%";

  syncFloorScaleToRug(mv);
  // Let extra-model apply scale transform before measuring bounds
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));

  const models = scene?._models;
  const floorModels =
    models && models.length >= 2 ? models.splice(1, models.length - 1) : [];

  try {
    if (scene && typeof scene.updateBoundingBox === "function") {
      scene.updateBoundingBox();
    }
    if (scene && typeof scene.updateFraming === "function") {
      await scene.updateFraming();
    } else if (typeof mv.updateFraming === "function") {
      await mv.updateFraming();
    }
  } catch (_) {
    /* ignore */
  } finally {
    if (models && floorModels.length) {
      for (const m of floorModels) {
        models.push(m);
        if (scene?.target && m.parent !== scene.target) scene.target.add(m);
        m.visible = currentFloorId !== "white" && !arPresenting;
      }
    }
  }

  mv.setAttribute("camera-orbit", orbit);
  mv.setAttribute("field-of-view", "28deg");
  queueMvRender(mv);
}

function pad4(bytes, fill = 0) {
  const rem = bytes.length % 4;
  if (rem === 0) return bytes;
  const out = new Uint8Array(bytes.length + (4 - rem));
  out.set(bytes);
  if (fill) out.fill(fill, bytes.length);
  return out;
}

function u32(n) {
  const b = new ArrayBuffer(4);
  new DataView(b).setUint32(0, n, true);
  return new Uint8Array(b);
}

function concatBytes(parts) {
  const total = parts.reduce((n, p) => n + p.length, 0);
  const out = new Uint8Array(total);
  let o = 0;
  for (const p of parts) {
    out.set(p, o);
    o += p.length;
  }
  return out;
}

/** Minimal textured XZ plane GLB for custom floor uploads. */
function buildFloorGlbFromImage(imageBytes, mimeType, sizeM = FLOOR_SIZE_M) {
  const w = sizeM;
  const hx = w / 2;
  const hz = w / 2;
  const y = 0;
  const positions = new Float32Array([
    -hx, y, -hz, hx, y, -hz, hx, y, hz, -hx, y, hz,
  ]);
  const normals = new Float32Array([0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0]);
  const uvs = new Float32Array([0, 1, 1, 1, 1, 0, 0, 0]);
  const indices = new Uint16Array([0, 2, 1, 0, 3, 2]);

  const posBuf = new Uint8Array(positions.buffer);
  const normBuf = new Uint8Array(normals.buffer);
  const uvBuf = new Uint8Array(uvs.buffer);
  const idxBuf = pad4(new Uint8Array(indices.buffer));
  const imgBuf = imageBytes instanceof Uint8Array ? imageBytes : new Uint8Array(imageBytes);

  let offset = 0;
  const posOff = offset;
  offset += posBuf.length;
  const normOff = offset;
  offset += normBuf.length;
  const uvOff = offset;
  offset += uvBuf.length;
  const idxOff = offset;
  offset += idxBuf.length;
  const imgOff = offset;
  const binary = concatBytes([posBuf, normBuf, uvBuf, idxBuf, imgBuf]);

  const gltf = {
    asset: { version: "2.0", generator: "mrCarpet-floor" },
    scene: 0,
    scenes: [{ nodes: [0] }],
    nodes: [{ mesh: 0, name: "ar-floor" }],
    meshes: [
      {
        name: "ar-floor",
        primitives: [
          {
            attributes: { POSITION: 0, NORMAL: 1, TEXCOORD_0: 2 },
            indices: 3,
            material: 0,
          },
        ],
      },
    ],
    materials: [
      {
        name: "floor",
        pbrMetallicRoughness: {
          baseColorTexture: { index: 0 },
          metallicFactor: 0,
          roughnessFactor: 1,
        },
        doubleSided: true,
        alphaMode: "OPAQUE",
      },
    ],
    textures: [{ source: 0 }],
    images: [{ bufferView: 4, mimeType: mimeType || "image/jpeg" }],
    buffers: [{ byteLength: binary.length }],
    bufferViews: [
      { buffer: 0, byteOffset: posOff, byteLength: posBuf.length, target: 34962 },
      { buffer: 0, byteOffset: normOff, byteLength: normBuf.length, target: 34962 },
      { buffer: 0, byteOffset: uvOff, byteLength: uvBuf.length, target: 34962 },
      { buffer: 0, byteOffset: idxOff, byteLength: idxBuf.length, target: 34963 },
      { buffer: 0, byteOffset: imgOff, byteLength: imgBuf.length },
    ],
    accessors: [
      {
        bufferView: 0,
        componentType: 5126,
        count: 4,
        type: "VEC3",
        max: [hx, y, hz],
        min: [-hx, y, -hz],
      },
      { bufferView: 1, componentType: 5126, count: 4, type: "VEC3" },
      { bufferView: 2, componentType: 5126, count: 4, type: "VEC2" },
      { bufferView: 3, componentType: 5123, count: 6, type: "SCALAR" },
    ],
  };

  const jsonBytes = pad4(
    new TextEncoder().encode(JSON.stringify(gltf)),
    0x20
  );
  const total = 12 + 8 + jsonBytes.length + 8 + binary.length;
  const magic = new Uint8Array([0x67, 0x6c, 0x54, 0x46]); // glTF
  const version = u32(2);
  const totalBuf = u32(total);
  const jsonLen = u32(jsonBytes.length);
  const jsonType = new Uint8Array([0x4a, 0x53, 0x4f, 0x4e]); // JSON
  const binLen = u32(binary.length);
  const binType = new Uint8Array([0x42, 0x49, 0x4e, 0x00]); // BIN\0
  return concatBytes([
    magic,
    version,
    totalBuf,
    jsonLen,
    jsonType,
    jsonBytes,
    binLen,
    binType,
    binary,
  ]);
}

function getFloorCycleIds() {
  const ids = FLOOR_PRESETS.map((f) => f.id);
  if (customFloorGlbUrl || currentFloorId === "custom") ids.push("custom");
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
  applyFloor(ids[(idx + delta + ids.length) % ids.length]);
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

async function applyFloor(floorId) {
  const token = ++floorApplyToken;
  currentFloorId = floorId || "white";
  const glbUrl = resolveFloorGlb(currentFloorId);
  const mv = modelViewerEl || document.querySelector(".product-ar-modal__mv");
  syncFloorChipActive();
  if (!mv) return;

  const extra = ensureFloorExtra(mv);
  setViewerChrome(mv, Boolean(glbUrl));

  if (!glbUrl) {
    if (extra.hasAttribute("src")) {
      const pending = waitForMvLoad(mv);
      extra.removeAttribute("src");
      await Promise.race([
        pending,
        new Promise((r) => setTimeout(r, 800)),
      ]);
    }
    if (token !== floorApplyToken) return;
    setFloorModelsVisible(mv, false);
    await reframedRugOnly(mv);
    return;
  }

  const currentSrc = extra.getAttribute("src");
  if (currentSrc !== glbUrl) {
    const pending = waitForMvLoad(mv);
    extra.setAttribute("src", glbUrl);
    await Promise.race([
      pending,
      new Promise((r) => setTimeout(r, 12000)),
    ]);
  }
  if (token !== floorApplyToken) return;

  setFloorModelsVisible(mv, !arPresenting);
  await reframedRugOnly(mv);
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
    if (floor.thumb) {
      btn.style.backgroundImage = `url("${floor.thumb}")`;
    } else {
      btn.classList.add("is-white");
    }
    btn.addEventListener("click", () => applyFloor(floor.id));
    list.appendChild(btn);
  });
}

function bindFloorUpload() {
  const input = document.getElementById("product-ar-floor-upload");
  if (!input || input.dataset.bound === "1") return;
  input.dataset.bound = "1";
  input.addEventListener("change", async () => {
    const file = input.files && input.files[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setStatus("Оберіть файл зображення для підлоги", true);
      return;
    }
    try {
      const buf = new Uint8Array(await file.arrayBuffer());
      const glbBytes = buildFloorGlbFromImage(buf, file.type || "image/jpeg");
      if (customFloorGlbUrl) URL.revokeObjectURL(customFloorGlbUrl);
      if (customFloorThumbUrl) URL.revokeObjectURL(customFloorThumbUrl);
      customFloorGlbUrl = URL.createObjectURL(
        new Blob([glbBytes], { type: "model/gltf-binary" })
      );
      customFloorThumbUrl = URL.createObjectURL(file);
      await applyFloor("custom");
    } catch (err) {
      console.error(err);
      setStatus("Не вдалося застосувати підлогу", true);
    }
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
    modelViewerEl.setAttribute("camera-orbit", "0deg 0deg 120%");
    modelViewerEl.setAttribute("field-of-view", "28deg");
    modelViewerEl.setAttribute("min-field-of-view", "16deg");
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
      setFloorModelsVisible(modelViewerEl, currentFloorId !== "white" && !arPresenting);
      if (status === "failed") {
        setStatus(
          "Не вдалося відкрити AR. Перевірте підтримку пристрою або скористайтесь QR-кодом.",
          true
        );
        showQr(currentSizeLabel);
      }
    });

    ensureFloorExtra(modelViewerEl);
    host.appendChild(modelViewerEl);
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

    // Floor as extra-model in the same scene; frame by rug only
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
  if (customFloorGlbUrl) {
    URL.revokeObjectURL(customFloorGlbUrl);
    customFloorGlbUrl = null;
  }
  if (customFloorThumbUrl) {
    URL.revokeObjectURL(customFloorThumbUrl);
    customFloorThumbUrl = null;
  }
  if (currentFloorId === "custom") {
    currentFloorId = "white";
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
