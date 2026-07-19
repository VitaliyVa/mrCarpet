import "./index.scss";

const HOVER_MQ = "(hover: hover) and (min-width: 769px)";

function loadHoverImage(wrap) {
  if (!wrap || wrap.querySelector("img")) return;
  const src = wrap.dataset.hoverSrc;
  if (!src) return;

  const img = document.createElement("img");
  img.src = src;
  img.alt = "";
  img.width = 365;
  img.height = 420;
  img.decoding = "async";
  img.setAttribute("aria-hidden", "true");
  wrap.appendChild(img);
}

function bindHoverLazyLoad() {
  if (!window.matchMedia(HOVER_MQ).matches) return;

  document
    .querySelectorAll(".cart_item_img.image-on-hover[data-hover-src]")
    .forEach((wrap) => {
      const card = wrap.closest(".cart_item");
      if (!card) return;

      const onEnter = () => loadHoverImage(wrap);
      card.addEventListener("mouseenter", onEnter, { once: true, passive: true });
    });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bindHoverLazyLoad, { once: true });
} else {
  bindHoverLazyLoad();
}
