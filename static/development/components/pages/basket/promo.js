import { addPromocode } from "../../../api/promo";
import { bad_modal, getFormFields } from "../../module/form_action";
import validation from "../../module/validation";

document.addEventListener("click", (event) => {
  event.preventDefault();

  const addPromoCodeButton = event.target.closest(".basket__promocode-add-btn");

  if (addPromoCodeButton) {
    const formValues = getFormFields(
      ".basket__promocode-form",
      ".input-transparent"
    );

    const status = validation(addPromoCodeButton);

    if (status) {
      addPromocode(formValues?.code);
    } else {
      bad_modal("Введіть промокод!");
    }
  }
});
