import { instance } from "./instance";
import { showLoader, hideLoader } from "../components/module/form_action";
import { showSuccess, showError } from "../utils/notifications";

export const sendReview = async (values) => {
  showLoader();

  try {
    const { data } = await instance.post("/product-reviews/", values);

    hideLoader();
    showSuccess(data?.message || "Ваш відгук успішно відправлено 🎉");

    // A Google review carries more weight for other shoppers than an
    // on-site one, and asking right after someone already wrote a review is
    // the one moment they're willing to write a second. Only shown once
    // GOOGLE_PLACE_ID is set (see core/settings.py) — inert otherwise.
    const googleReviewUrl = document.querySelector(".product")?.dataset
      ?.googleReviewUrl;
    if (googleReviewUrl) {
      setTimeout(
        () =>
          showSuccess(
            `Дякуємо! Поділіться враженням також <a href="${googleReviewUrl}" target="_blank" rel="noopener" style="color:inherit;text-decoration:underline;">у Google →</a>`
          ),
        1600
      );
    }

    setTimeout(() => window.location.reload(), googleReviewUrl ? 6000 : 1500);

    return data;
  } catch ({ response }) {
    hideLoader();
    showError(response?.data?.message || "Упс... щось пішло не так");
  }
};
