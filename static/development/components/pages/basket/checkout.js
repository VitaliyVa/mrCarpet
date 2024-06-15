import { createOrder } from "../../../api/checkout";
import { bad_modal, getFormFields } from "../../module/form_action";
import validation from "../../module/validation";

const checkboxItems = document.querySelectorAll(".basket__checkbox-item");

document.addEventListener("click", ({ target }) => {
  const accordionTitle = target.closest(".accordion__title");
  const bodyBlockEditBtn = target.closest(
    ".basket__checkbox-item-body-block-edit-btn"
  );

  // Control accordion and checkboxes
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

  // Unlocking editing of address and contact data fields
  if (bodyBlockEditBtn) {
    const bodyBlock = bodyBlockEditBtn.closest(
      ".basket__checkbox-item-body-block"
    );
    const bodyBlockFields = bodyBlock.querySelectorAll("input");

    if (bodyBlockEditBtn.classList.contains("active")) {
      bodyBlockEditBtn.classList.remove("active");
      bodyBlockFields.forEach((item) => (item.readOnly = true));
    } else {
      bodyBlockEditBtn.classList.add("active");
      bodyBlockFields.forEach((item) => (item.readOnly = false));
    }
  }
});

document.addEventListener("click", (event) => {
  event.preventDefault();

  const submitOrderButton = event.target.closest(".");

  if (submitOrderButton) {
    const formValues = {};

    // addPromocode(formValues?.code);
  }
});
