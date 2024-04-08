import "./index.scss";
import "./orders.scss";
import "./profile-modal.scss";

import { updateCurrentUser } from "../../../api/currentUser";
import { getFormFields } from "../../module/form_action";
import validation from "../../module/validation";

const saveChangesButton = document.querySelector(
  ".profile-modal__save-changes-btn"
);

const updatePasswordButton = document.querySelector(
  ".profile-modal__update-password-btn"
);

if (saveChangesButton) {
  saveChangesButton.addEventListener("click", async (event) => {
    event.preventDefault();

    const formValues = getFormFields(
      ".profile-modal__form-edit-profile",
      ".validation_input"
    );

    const status = validation(saveChangesButton);

    if (status) {
      await updateCurrentUser(formValues);
    }
  });
}

if (updatePasswordButton) {
  updatePasswordButton.addEventListener("click", async (event) => {
    event.preventDefault();

    const formValues = getFormFields(
      ".profile-modal__form-change-password",
      ".validation_input"
    );

    const status = validation(updatePasswordButton);

    if (status) {
      await updateCurrentUser(formValues);
    }
  });
}
