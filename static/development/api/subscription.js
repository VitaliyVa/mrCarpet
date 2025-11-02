import { instance } from "./instance";
import { showLoader, hideLoader } from "../components/module/form_action";
import { showSuccess, showError } from "../utils/notifications";

export const subscribeToNewsletter = async (email) => {
  try {
    showLoader();

    const { data } = await instance.post("/subscription/", {
      email,
    });

    hideLoader();
    showSuccess(
      data?.message ||
        "Ви успішно підписалися на розсилку новин та акцій 🎉"
    );

    return data;
  } catch ({ response }) {
    hideLoader();
    showError(response?.data?.message || "Упс... щось пішло не так");
  }
};
