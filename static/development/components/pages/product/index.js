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

function updateProductAiNote(swiper) {
  const note = document.getElementById("product-ai-note");
  if (!note) return;

  const slide = swiper.slides[swiper.activeIndex];
  const isAi = slide?.dataset?.isAi === "1";
  note.hidden = !isAi;
}

product_main_swiper.on("slideChange", updateProductAiNote);
updateProductAiNote(product_main_swiper);
