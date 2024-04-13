import { subscribeToNewsletter } from "../../../api/subscription";
import { getFormFields } from "../../module/form_action";
import validation from "../../module/validation";

const subscribeButton = document.querySelector(".subscribe-btn");

if (subscribeButton) {
  subscribeButton.addEventListener("click", async (event) => {
    event.preventDefault();

    const formValues = getFormFields(".subscription-form", ".validation_input");

    const status = validation(subscribeButton);

    if (status) {
      await subscribeToNewsletter(formValues.email);
    }
  });
}
