import { instance } from "./instance";
import { showLoader, hideLoader } from "../components/module/form_action";
import { showSuccess, showError } from "../utils/notifications";
import { trackEvent } from "../utils/analytics";

export const sendContactForm = async (values) => {
  showLoader();

  try {
    const { data } = await instance.post("/contact/", values);

    hideLoader();
    trackEvent("generate_lead", {
      lead_type: "contact_form",
      method: "contact",
    });
    showSuccess("Повідомлення успішно відправлено!");
    setTimeout(() => window.location.reload(), 1500);

    return data;
  } catch ({ response }) {
    hideLoader();
    showError(response?.data?.message || "Помилка відправки повідомлення");
  }
};
