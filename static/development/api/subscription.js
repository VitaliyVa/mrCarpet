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
    return data;
  } catch ({ response }) {
    hideLoader();

    const payload = response?.data || {};
    // Уже підписаний — все одно віддаємо промокод у модалку
    if (payload.welcome_promocode) {
      return {
        ...payload,
        already_subscribed: true,
      };
    }

    showError(payload.message || "Упс... щось пішло не так");
    return null;
  }
};
