import PhotoSwipeLightbox from "photoswipe/dist/photoswipe-lightbox.esm.js";
import PhotoSwipe from "photoswipe/dist/photoswipe.esm.js";
import "photoswipe/dist/photoswipe.css";

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
  if (img.naturalWidth > 0 && img.naturalHeight > 0) {
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
    items.push({
      src: img.currentSrc || img.src,
      width,
      height,
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

  const getDataSource = () => {
    if (!dataSourcePromise) {
      dataSourcePromise = buildDataSource();
    }
    return dataSourcePromise;
  };

  // Warm cache after first paint — images usually already in DOM
  requestAnimationFrame(() => {
    getDataSource();
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
