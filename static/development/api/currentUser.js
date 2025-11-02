import { instance } from "./instance";
import { showLoader, hideLoader } from "../components/module/form_action";
import { showSuccess, showError } from "../utils/notifications";

export const updateCurrentUser = async (values) => {
  showLoader();

  try {
    const { data } = await instance.patch("/users/update_profile/", values);

    hideLoader();
    showSuccess("Зміни успішно збережено!");
    setTimeout(() => window.location.reload(), 1500);

    return data;
  } catch ({ response }) {
    hideLoader();
    showError(response?.data?.message || "Помилка збереження змін");
  }
};
