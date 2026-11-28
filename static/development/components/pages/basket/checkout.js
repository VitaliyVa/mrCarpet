import { initPromocode, restorePromocode } from "./promocode";
import { initNovaPost, getNovaPostData, prefillNovaPost } from "./nova-post";
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
initStickyConfirm();

// On a phone the confirm button sits at the very bottom, under the summary.
// While it is still below the screen, a bar with the total and a copy of the
// button stays at the bottom; it disappears once the real button is visible.
function initStickyConfirm() {
  const bar = document.getElementById("checkout-sticky-bar");
  const mainBtn = document.querySelector(".basket__to-order-btn");
  if (!bar || !mainBtn || !("IntersectionObserver" in window)) return;

  const stickyBtn = bar.querySelector(".basket__sticky-btn");
  const stickyTotal = document.getElementById("checkout-sticky-total");
  const totalEl = document.querySelector(".basket__calculate-total-price-value");
  const phone = window.matchMedia("(max-width: 720px)");

  stickyBtn?.addEventListener("click", () => mainBtn.click());

  const setVisible = (show) => {
    bar.hidden = !show;
    document.body.classList.toggle("has-checkout-sticky-bar", show);
    if (show && stickyTotal && totalEl) {
      stickyTotal.textContent = totalEl.textContent.trim();
    }
  };

  let below = false;
  const update = () => setVisible(phone.matches && below);

  new IntersectionObserver(([entry]) => {
    below = !entry.isIntersecting && entry.boundingClientRect.top > 0;
    update();
  }).observe(mainBtn);

  phone.addEventListener?.("change", update);
}

document.addEventListener("DOMContentLoaded", () => {
  restorePromocode();

  const saved = window.__CHECKOUT_USER__;
  if (saved && typeof saved === "object") {
    prefillNovaPost({
      name: saved.name || "",
      email: saved.email || "",
      phone: saved.phone || "",
      city: saved.city || "",
      settlementRef: saved.settlementRef || "",
      warehouseId: saved.warehouseId || "",
      warehouseTitle: saved.warehouseTitle || "",
      warehouseRef: saved.warehouseRef || "",
    });
  }
});

export { getNovaPostData };
