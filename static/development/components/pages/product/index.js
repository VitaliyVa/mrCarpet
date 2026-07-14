import Swiper, { Thumbs, Navigation } from "swiper";
import "swiper/swiper-bundle.css";
import "choices.js/public/assets/styles/choices.min.css";
import "./product";
import "./reviews";
import "./index.scss";
import "./review-write-modal.scss";

Swiper.use([Thumbs, Navigation]);

const product_main_swiper = new Swiper(".product_slider_main", {
  slidesPerView: 1,
  slidesPerGroup: 1,
  initialSlide: 0,
  autoHeight: true,
  // zoom: {
  //     maxRaito: 5,
  //     minRaito: 1
  // },
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
      breakpoints: {
        // 700: {
        //   slidesPerView: 4,
        // },
        // 600: {
        //   slidesPerView: 3,
        // },
        // 300: {
        //   slidesPerView: 2,
        // },
      },
    },
  },
});

function positionBadgeTooltip(badge) {
  const tooltip = badge.querySelector(".product-slide__badge-tooltip");
  const label = badge.querySelector(".product-slide__badge-label");
  if (!tooltip || !label) return;

  tooltip.style.visibility = "hidden";
  tooltip.style.opacity = "0";
  tooltip.style.display = "block";

  const tooltipRect = tooltip.getBoundingClientRect();
  const labelRect = label.getBoundingClientRect();
  const gap = 8;
  const margin = 12;

  let top = labelRect.top - tooltipRect.height - gap;
  let left = labelRect.left;

  if (top < margin) {
    top = labelRect.bottom + gap;
  }

  if (left + tooltipRect.width > window.innerWidth - margin) {
    left = window.innerWidth - tooltipRect.width - margin;
  }

  if (left < margin) {
    left = margin;
  }

  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
  tooltip.style.visibility = "";
  tooltip.style.opacity = "";
  tooltip.style.display = "";
}

function openBadge(badge) {
  positionBadgeTooltip(badge);
  badge.classList.add("product-slide__badge--open");
}

function closeBadge(badge) {
  badge.classList.remove("product-slide__badge--open");
}

function initProductAiBadges() {
  const badges = document.querySelectorAll(".product-slide__badge");
  if (!badges.length) return;

  const hasHover = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
  const hideTimers = new WeakMap();

  const scheduleClose = (badge) => {
    clearTimeout(hideTimers.get(badge));
    hideTimers.set(
      badge,
      setTimeout(() => closeBadge(badge), 140)
    );
  };

  const cancelClose = (badge) => {
    clearTimeout(hideTimers.get(badge));
  };

  badges.forEach((badge) => {
    const tooltip = badge.querySelector(".product-slide__badge-tooltip");

    if (hasHover) {
      [badge, tooltip].forEach((el) => {
        if (!el) return;
        el.addEventListener("mouseenter", () => {
          cancelClose(badge);
          openBadge(badge);
        });
        el.addEventListener("mouseleave", () => scheduleClose(badge));
      });
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

  window.addEventListener("resize", () => {
    badges.forEach((badge) => {
      if (badge.classList.contains("product-slide__badge--open")) {
        positionBadgeTooltip(badge);
      }
    });
  });

  document.addEventListener("click", (event) => {
    if (event.target.closest(".product-slide__badge")) return;
    badges.forEach((badge) => closeBadge(badge));
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      badges.forEach((badge) => closeBadge(badge));
    }
  });
}

initProductAiBadges();
