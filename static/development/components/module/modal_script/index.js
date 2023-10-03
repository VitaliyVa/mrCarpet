import "./index.scss";

let all_modals = document.querySelectorAll(".modal__block");
let modal_close = document.querySelectorAll(".modal_close");

let modal_open = document.querySelectorAll(".modal_open");

modal_open.forEach((element) => {
  let modal_block = document.querySelector(`.${element.dataset.href}`);
  element.addEventListener("click", function () {
    all_modals.forEach((modal) => {
      const overlay = modal.closest(".modal-overlay");

      modal.classList.remove("active");

      if (overlay) {
        overlay.classList.remove("active");
      }

      document.body.style.overflow = "auto";
    });
    const overlay_block = modal_block.closest(".modal-overlay");

    modal_block.classList.add("active");

    if (overlay_block) {
      overlay_block.classList.add("active");
      document.body.style.overflow = "hidden";
    }
  });
});

all_modals.forEach((element) => {
  document.body.addEventListener("click", (e) => {
    const target = e.target;
    let check = element.classList.contains("active");

    if (
      !target.closest(".modal__block") &&
      !target.closest(".modal_open") &&
      check
    ) {
      const overlay = element.closest(".modal-overlay");
      const isNotCloseOutside = overlay.dataset?.isNotCloseOutside;

      if (!isNotCloseOutside) {
        element.classList.remove("active");
      }

      if (overlay && !isNotCloseOutside) {
        overlay.classList.remove("active");
      }

      document.body.style.overflow = "auto";
    }
  });
});

modal_close.forEach((element) => {
  let wrapper = element.closest(".modal__block");
  element.addEventListener("click", function () {
    const overlay = wrapper.closest(".modal-overlay");

    wrapper.classList.remove("active");

    if (overlay) {
      overlay.classList.remove("active");
    }

    document.body.style.overflow = "auto";
  });
});
