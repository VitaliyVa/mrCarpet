import { instance } from "./instance";
import { showLoader, hideLoader } from "../components/module/form_action";
import { showSuccess, showError } from "../utils/notifications";

// A review that waits for moderation is not on the page after a reload, so
// reloading only made it look lost. Close the form instead and leave the
// "thank you, it will appear after a check" note on screen.
const closeReviewForm = () => {
  const overlay = document.querySelector(".review-write-modal-overlay");
  if (!overlay) return;

  const content = overlay.querySelector("#content");
  if (content) content.value = "";

  overlay.querySelector(".review-write-modal")?.classList.remove("active");
  overlay.classList.remove("active");
  document.body.classList.remove("lock");
  document.body.style.overflowY = "initial";
};

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

    // Older API responses carry no flag; treat those as published so the
    // page behaves exactly as before.
    if (data?.published === false) {
      closeReviewForm();
    } else {
      setTimeout(() => window.location.reload(), googleReviewUrl ? 6000 : 1500);
    }

    return data;
  } catch ({ response }) {
    hideLoader();
    showError(response?.data?.message || "Упс... щось пішло не так");
  }
};
