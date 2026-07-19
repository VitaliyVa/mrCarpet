import { instance } from "./instance";
import { showLoader, hideLoader } from "../components/module/form_action";
import { showSuccess, showError } from "../utils/notifications";
import { trackEvent } from "../utils/analytics";

export const subscribeToNewsletter = async (email) => {
  try {
    showLoader();

    const { data } = await instance.post("/subscription/", {
      email,
    });

    hideLoader();
    trackEvent("generate_lead", {
      lead_type: "newsletter",
      method: "subscribe",
    });
    return data;
  } catch ({ response }) {
    hideLoader();

    const payload = response?.data || {};
    // Уже підписаний — все одно віддаємо промокод у модалку
    if (payload.welcome_promocode) {
      trackEvent("generate_lead", {
        lead_type: "newsletter",
        method: "already_subscribed",
      });
      return {
        ...payload,
        already_subscribed: true,
      };
    }

    const fieldError = Array.isArray(payload.email)
      ? payload.email[0]
      : payload.email;
    showError(payload.message || fieldError || "Упс... щось пішло не так");
    return null;
  }
};
