import "./index.scss";
import "./review-write-modal.scss";
import "./star_rate.scss";

import Swiper, { Thumbs, Navigation } from "swiper";
import "swiper/swiper-bundle.css";

Swiper.use([Thumbs]);

const product_main_swiper = new Swiper(".product_slider_main", {
  slidesPerView: 1,
  slidesPerGroup: 1,
  initialSlide: 0,
  // zoom: {
  //     maxRaito: 5,
  //     minRaito: 1
  // },

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
