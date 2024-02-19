import { registerUser } from "../../../api/auth";
import { getFormFields } from "../../module/form_action";
import validation from "../../module/validation";

const loginButton = document.querySelector(
  ".register-modal__create-account-btn"
);
const registerButton = document.querySelector(
  ".register-modal__create-account-btn"
);

// if (loginButton) {
// }

if (registerButton) {
  registerButton.addEventListener("click", async (event) => {
    event.preventDefault();

    const formValues = getFormFields(
      ".register-modal__form",
      ".validation_input"
    );

    const status = validation(registerButton);

    if (status) {
      const data = await registerUser(formValues);

      console.log(data);
    }
  });
}
