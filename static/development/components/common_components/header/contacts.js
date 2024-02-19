import { sendContactForm } from "../../../api/contacts";
import { getFormFields } from "../../module/form_action";
import validation from "../../module/validation";

const sendButton = document.querySelector(
  ".contacts-modal__send-application-btn"
);

if (sendButton) {
  sendButton.addEventListener("click", async (event) => {
    event.preventDefault();

    const formValues = getFormFields(
      ".contacts-modal__feedback-form",
      ".validation_input"
    );

    const status = validation(sendButton);

    if (status) {
      await sendContactForm(formValues);
    }
  });
}
