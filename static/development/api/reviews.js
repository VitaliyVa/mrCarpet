import { instance } from "./instance";
import { showLoader, hideLoader } from "../components/module/form_action";
import { showSuccess, showError } from "../utils/notifications";

export const sendReview = async (values) => {
  showLoader();

  try {
    const { data } = await instance.post("/product-reviews/", values);

    hideLoader();
    showSuccess(data?.message || "Ваш відгук успішно відправлено 🎉");
    setTimeout(() => window.location.reload(), 1500);

    return data;
  } catch ({ response }) {
    hideLoader();
    showError(response?.data?.message || "Упс... щось пішло не так");
  }
};
