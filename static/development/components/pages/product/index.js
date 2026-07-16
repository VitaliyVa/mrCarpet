import Swiper, { Thumbs, Navigation } from "swiper";
import "swiper/swiper-bundle.css";
import "choices.js/public/assets/styles/choices.min.css";
import "./product";
import "./reviews";
import "./index.scss";
import "./review-write-modal.scss";
import { initProductArViewer } from "./ar-viewer";
import { initProductGalleryLightbox } from "./gallery-lightbox";

Swiper.use([Thumbs, Navigation]);

const product_main_swiper = new Swiper(".product_slider_main", {
  slidesPerView: 1,
  slidesPerGroup: 1,
  initialSlide: 0,
  // Desktop: height follows image. Mobile: CSS max-height caps gallery;
  // autoHeight still used so short images don't leave empty space.
  autoHeight: true,
  navigation: {
    nextEl: ".swiper-button-next",
    prevEl: ".swiper-button-prev",
  },

  thumbs: {
    swiper: {
      el: ".product_slider_mini",
      slidesPerView: 6,
      spaceBetween: 16,
      direction: "vertical",
      breakpoints: {},
    },
  },
  on: {
    init(swiper) {
      // Recalc after images paint — prevents tall photos overlapping text on mobile
      swiper.el.querySelectorAll("img").forEach((img) => {
        if (img.complete) return;
        img.addEventListener(
          "load",
          () => {
            swiper.updateAutoHeight(0);
          },
          { once: true }
        );
      });
      requestAnimationFrame(() => swiper.updateAutoHeight(0));
    },
  },
});

if (typeof window !== "undefined") {
  window.addEventListener("resize", () => {
    product_main_swiper.updateAutoHeight(0);
  });
}

initProductGalleryLightbox(product_main_swiper);

function positionBadgeTooltip(anchor, tooltip) {
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
  let left = rect.left;

  if (top < margin) {
    top = rect.bottom + gap;
  }

  if (left + tooltipWidth > window.innerWidth - margin) {
    left = window.innerWidth - tooltipWidth - margin;
  }

  if (left < margin) {
    left = margin;
  }

  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
  tooltip.style.visibility = "";
}

function openBadge(badge) {
  const tooltip = badge.querySelector(".product-slide__badge-tooltip")
    || document.querySelector(
      `.product-slide__badge-tooltip[data-badge-for="${badge.dataset.badgeId}"]`
    );
  const label = badge.querySelector(".product-slide__badge-label");
  if (!tooltip || !label) return;

  if (tooltip.parentElement !== document.body) {
    document.body.appendChild(tooltip);
  }

  positionBadgeTooltip(label, tooltip);
  tooltip.classList.add("is-visible");
  badge.classList.add("product-slide__badge--open");
}

function closeBadge(badge) {
  const tooltip = document.querySelector(
    `.product-slide__badge-tooltip[data-badge-for="${badge.dataset.badgeId}"]`
  ) || badge.querySelector(".product-slide__badge-tooltip");

  badge.classList.remove("product-slide__badge--open");

  if (!tooltip) return;

  tooltip.classList.remove("is-visible");
  badge.appendChild(tooltip);
}

function initProductAiBadges() {
  const badges = document.querySelectorAll(".product-slide__badge");
  if (!badges.length) return;

  const hasHover = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
  const hideTimers = new WeakMap();

  badges.forEach((badge, index) => {
    const tooltip = badge.querySelector(".product-slide__badge-tooltip");
    const badgeId = `badge-${index}`;
    badge.dataset.badgeId = badgeId;

    if (tooltip) {
      tooltip.dataset.badgeFor = badgeId;
    }

    const scheduleClose = () => {
      clearTimeout(hideTimers.get(badge));
      hideTimers.set(
        badge,
        setTimeout(() => closeBadge(badge), 160)
      );
    };

    const cancelClose = () => {
      clearTimeout(hideTimers.get(badge));
    };

    if (hasHover) {
      badge.addEventListener("mouseenter", () => {
        cancelClose();
        openBadge(badge);
      });

      badge.addEventListener("mouseleave", scheduleClose);

      if (tooltip) {
        tooltip.addEventListener("mouseenter", cancelClose);
        tooltip.addEventListener("mouseleave", scheduleClose);
      }
    }

    badge.addEventListener("focus", () => openBadge(badge));
    badge.addEventListener("blur", () => closeBadge(badge));

    badge.addEventListener("click", (event) => {
      if (hasHover) return;

      event.stopPropagation();
      const isOpen = badge.classList.contains("product-slide__badge--open");
      badges.forEach((item) => closeBadge(item));
      if (!isOpen) openBadge(badge);
    });
  });

  product_main_swiper.on("slideChange", () => {
    badges.forEach((badge) => closeBadge(badge));
  });

  window.addEventListener("resize", () => {
    badges.forEach((badge) => {
      if (!badge.classList.contains("product-slide__badge--open")) return;

      const tooltip = document.querySelector(
        `.product-slide__badge-tooltip[data-badge-for="${badge.dataset.badgeId}"]`
      );
      const label = badge.querySelector(".product-slide__badge-label");
      if (tooltip && label) {
        positionBadgeTooltip(label, tooltip);
      }
    });
  });

  document.addEventListener("click", (event) => {
    if (event.target.closest(".product-slide__badge")) return;
    if (event.target.closest(".product-slide__badge-tooltip")) return;
    badges.forEach((badge) => closeBadge(badge));
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      badges.forEach((badge) => closeBadge(badge));
    }
  });
}

initProductAiBadges();
initProductArViewer();
