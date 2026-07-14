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

function initProductAiBadges() {
  const badges = document.querySelectorAll(".product-slide__badge");
  if (!badges.length) return;

  const hasHover = window.matchMedia("(hover: hover)").matches;

  badges.forEach((badge) => {
    badge.addEventListener("click", (event) => {
      if (hasHover) return;

      event.stopPropagation();
      const isOpen = badge.classList.contains("product-slide__badge--open");
      badges.forEach((item) => item.classList.remove("product-slide__badge--open"));
      if (!isOpen) badge.classList.add("product-slide__badge--open");
    });
  });

  document.addEventListener("click", () => {
    badges.forEach((badge) => badge.classList.remove("product-slide__badge--open"));
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      badges.forEach((badge) => badge.classList.remove("product-slide__badge--open"));
    }
  });
}

initProductAiBadges();
