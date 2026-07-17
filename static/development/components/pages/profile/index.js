import "./index.scss";
import "./orders.scss";
import "./profile-modal.scss";
import "../basket/nova-post.scss";

import { updateCurrentUser } from "../../../api/currentUser";
import { getFormFields } from "../../module/form_action";
import validation from "../../module/validation";
import {
  initNovaPost,
  getNovaPostData,
  prefillNovaPost,
} from "../basket/nova-post";

const saveChangesButton = document.querySelector(
  ".profile-modal__save-changes-btn"
);

const updatePasswordButton = document.querySelector(
  ".profile-modal__update-password-btn"
);

initNovaPost();

const profileForm = document.getElementById("profile-edit-form");
if (profileForm) {
  const city =
    profileForm.dataset.deliveryCity ||
    document.getElementById("nova-post-city-input")?.value ||
    "";
  const settlementRef = profileForm.dataset.settlementRef || "";
  if (city && settlementRef) {
    prefillNovaPost({
      city,
      settlementRef,
      warehouseId: profileForm.dataset.warehouseId || "",
      warehouseTitle: profileForm.dataset.warehouseTitle || "",
      warehouseRef: profileForm.dataset.warehouseRef || "",
    });
  }
}

if (saveChangesButton) {
  saveChangesButton.addEventListener("click", async (event) => {
    event.preventDefault();

    const formValues = getFormFields(
      ".profile-modal__form-edit-profile",
      ".validation_input"
    );

    const status = validation(saveChangesButton);

    if (!status) return;

    const cityInput = document.getElementById("nova-post-city-input");
    const np = getNovaPostData();
    const city =
      np.settlement?.title || cityInput?.value?.trim() || "";

    await updateCurrentUser({
      ...formValues,
      delivery_city: city,
      delivery_settlement_ref: np.settlement?.ref || "",
      delivery_warehouse: np.warehouse?.title || "",
      delivery_warehouse_ref: np.warehouse?.ref || "",
      delivery_warehouse_id: np.warehouse?.id || "",
    });
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
