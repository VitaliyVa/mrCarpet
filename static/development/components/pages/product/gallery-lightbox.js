import PhotoSwipeLightbox from "photoswipe/dist/photoswipe-lightbox.esm.js";
import PhotoSwipe from "photoswipe/dist/photoswipe.esm.js";
import "photoswipe/dist/photoswipe.css";
import { trackEvent } from "../../../utils/analytics";

function getMainImageSlides() {
  return Array.from(
    document.querySelectorAll(
      ".product_slider_main .swiper-slide:not(.product-ar-main-slide)"
    )
  );
}

function getMiniImageSlides() {
  return Array.from(
    document.querySelectorAll(
      ".product_slider_mini .swiper-slide:not(.product-ar-thumb-slide)"
    )
  );
}

function readImageSize(img) {
  // > 1: slides 2+ start as a 1x1 placeholder GIF until _base.html swaps
  // their data-defer-src in, and that size must not reach PhotoSwipe.
  if (img.naturalWidth > 1 && img.naturalHeight > 1) {
    return Promise.resolve({
      width: img.naturalWidth,
      height: img.naturalHeight,
    });
  }

  return new Promise((resolve) => {
    const done = () =>
      resolve({
        width: img.naturalWidth || 1200,
        height: img.naturalHeight || 1200,
      });

    if (typeof img.decode === "function") {
      img.decode().then(done).catch(done);
      return;
    }

    img.addEventListener("load", done, { once: true });
    img.addEventListener("error", done, { once: true });
  });
}

async function buildDataSource() {
  const slides = getMainImageSlides();
  const items = [];

  for (const slide of slides) {
    const img = slide.querySelector("img");
    if (!img || !img.src) continue;

    const { width, height } = await readImageSize(img);
    // The slide shows a srcset WebP (≤1200 px); the lightbox opens the original
    // upload. Only the aspect ratio of the slide is trusted, so scale the
    // declared size up to roughly the original's — it caps the zoom level.
    const fullSrc = img.dataset.fullSrc || "";
    const shown = img.currentSrc || img.src;
    const scale =
      fullSrc && fullSrc !== shown
        ? Math.max(1, 1600 / Math.max(width, height, 1))
        : 1;
    items.push({
      src: fullSrc || shown,
      width: Math.round(width * scale),
      height: Math.round(height * scale),
      alt: img.alt || "",
      element: img,
    });
  }

  return items;
}

function slideIndexFromEventTarget(target) {
  const mainSlide = target.closest(
    ".product_slider_main .swiper-slide:not(.product-ar-main-slide)"
  );
  if (mainSlide) {
    return getMainImageSlides().indexOf(mainSlide);
  }

  const miniSlide = target.closest(
    ".product_slider_mini .swiper-slide:not(.product-ar-thumb-slide)"
  );
  if (miniSlide) {
    return getMiniImageSlides().indexOf(miniSlide);
  }

  return -1;
}

export function initProductGalleryLightbox(mainSwiper) {
  const galleryRoot = document.querySelector(".product_slider");
  if (!galleryRoot || !mainSwiper) return;

  let dataSourcePromise = null;

  const hasDeferredImages = () =>
    !!galleryRoot.querySelector("img[data-defer-src]");

  const getDataSource = () => {
    if (!dataSourcePromise) {
      // Opening the gallery needs every slide's real picture.
      if (hasDeferredImages() && typeof window.mrcLoadDeferredImages === "function") {
        window.mrcLoadDeferredImages();
      }
      dataSourcePromise = buildDataSource();
    }
    return dataSourcePromise;
  };

  // Warm cache after first paint — unless slides are still deferred: forcing
  // them in here would undo the deferral (they load after window load).
  requestAnimationFrame(() => {
    if (!hasDeferredImages()) getDataSource();
  });

  const lightbox = new PhotoSwipeLightbox({
    dataSource: [],
    pswpModule: PhotoSwipe,
    showHideAnimationType: "zoom",
    bgOpacity: 0.92,
    padding: { top: 24, bottom: 24, left: 16, right: 16 },
    wheelToZoom: true,
  });

  lightbox.addFilter("thumbEl", (thumbEl, data) => {
    if (data && data.element) return data.element;
    return thumbEl;
  });

  lightbox.addFilter("placeholderSrc", (placeholderSrc, slide) => {
    if (slide.data && slide.data.element) {
      return slide.data.element.currentSrc || slide.data.element.src;
    }
    return placeholderSrc;
  });

  lightbox.init();

  const openAt = async (index) => {
    if (index < 0) return;

    const dataSource = await getDataSource();
    if (!dataSource.length || index >= dataSource.length) return;

    lightbox.options.dataSource = dataSource;
    lightbox.loadAndOpen(index);

    const product = document.querySelector(".product[data-catalog-product-id]");
    trackEvent("gallery_open", {
      item_id: product?.dataset.catalogProductId || "",
      image_index: index,
      image_count: dataSource.length,
    });
  };

  galleryRoot.addEventListener("click", (event) => {
    if (event.target.closest(".product-slide__badge")) return;
    if (event.target.closest(".product-ar-thumb-btn")) return;
    if (event.target.closest("[data-ar-open-trigger]")) return;
    if (event.target.closest(".swiper-button")) return;

    const index = slideIndexFromEventTarget(event.target);
    if (index < 0) return;

    event.preventDefault();
    openAt(index);
  });

  galleryRoot.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;

    const index = slideIndexFromEventTarget(event.target);
    if (index < 0) return;

    event.preventDefault();
    openAt(index);
  });

  // Sync swiper when lightbox closes on a different slide
  lightbox.on("change", () => {
    if (!lightbox.pswp) return;
    const idx = lightbox.pswp.currIndex;
    if (typeof idx === "number" && mainSwiper.activeIndex !== idx) {
      mainSwiper.slideTo(idx);
    }
  });

  return lightbox;
}
