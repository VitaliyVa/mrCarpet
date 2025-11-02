import { instance } from "./instance";
import { showLoader, hideLoader } from "../components/module/form_action";
import { showSuccess, showError } from "../utils/notifications";

export const loginUser = async (values) => {
  showLoader();

  try {
    const { data } = await instance.post("/users/user_login/", values);

    hideLoader();
    showSuccess("Успішно!");
    setTimeout(() => window.location.reload(), 1500);

    return data;
  } catch ({ response }) {
    hideLoader();
    showError(response?.data?.message || "Помилка авторизації");
  }
};

export const registerUser = async (values) => {
  showLoader();

  try {
    const { data } = await instance.post("/users/register/", values);

    hideLoader();
    showSuccess("Успішно!");
    setTimeout(() => window.location.reload(), 1500);

    return data;
  } catch ({ response }) {
    hideLoader();
    showError(response?.data?.message || "Помилка реєстрації");
  }
};
