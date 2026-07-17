import { initPromocode, restorePromocode } from "./promocode";
import { initNovaPost, getNovaPostData } from "./nova-post";
import { initOrderForm } from "./order-form";

const checkboxItems = document.querySelectorAll(".basket__checkbox-item");

document.addEventListener("click", ({ target }) => {
  const accordionTitle = target.closest(".accordion__title");

  if (accordionTitle) {
    const accordionContentBlock = accordionTitle.closest(
      ".accordion_content__block"
    );
    const checkboxInput =
      accordionContentBlock.querySelector(".checkbox__input");

    checkboxInput.checked = true;
    accordionContentBlock.classList.add("active");

    checkboxItems.forEach((item) => {
      if (!item.querySelector(".checkbox__input").checked) {
        item.classList.remove("active");
      }
    });
  }
});

initPromocode();
initNovaPost();
initOrderForm();

document.addEventListener("DOMContentLoaded", () => {
  restorePromocode();
});

export { getNovaPostData };
