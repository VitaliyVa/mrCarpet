import "./index.scss";
import Swiper, { Navigation } from "swiper";
import "swiper/swiper-bundle.css";
import "./index.scss";

Swiper.use([Navigation]);

const productsSwiper = new Swiper(".products-swiper", {
  slidesPerView: "auto",
  spaceBetween: 16,

  navigation: {
    nextEl: ".swiper-button-next",
    prevEl: ".swiper-button-prev",
  },

  breakpoints: {
    0: {
      spaceBetween: 14,
    },

    600: {
      spaceBetween: 16,
    },
  },
});

const blogSwiper = new Swiper(".blog-swiper", {
  slidesPerView: "auto",
  // spaceBetween: 0,

  navigation: {
    nextEl: ".swiper-button-next",
    prevEl: ".swiper-button-prev",
  },
});
