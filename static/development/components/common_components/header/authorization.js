import { loginUser, registerUser } from "../../../api/auth";
import { getFormFields } from "../../module/form_action";
import validation from "../../module/validation";

const loginButton = document.querySelector(".login-modal__sign-in-btn");
const registerButton = document.querySelector(
  ".register-modal__create-account-btn"
);

if (loginButton) {
  loginButton.addEventListener("click", async (event) => {
    event.preventDefault();

    const formValues = getFormFields(".login-modal__form", ".validation_input");

    const status = validation(loginButton);

    if (status) {
      await loginUser(formValues);
    }
  });
}

if (registerButton) {
  registerButton.addEventListener("click", async (event) => {
    event.preventDefault();

    const formValues = getFormFields(
      ".register-modal__form",
      ".validation_input"
    );

    const status = validation(registerButton);

    if (status) {
      await registerUser(formValues);
    }
  });
}
