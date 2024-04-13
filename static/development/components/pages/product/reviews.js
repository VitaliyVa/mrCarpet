import { sendReview } from "../../../api/reviews";
import { bad_modal, getFormFields } from "../../module/form_action";
import validation from "../../module/validation";

const sendReviewButton = document.querySelector(
  ".review-write-modal__send-review-btn"
);

if (sendReviewButton) {
  sendReviewButton.addEventListener("click", async (event) => {
    event.preventDefault();

    const product = document.querySelector(".product");

    if (product) {
      const productId = product?.dataset?.productId;

      const ratingElement = document.querySelector(".star-rate");
      const rating = Number(ratingElement.dataset.ratingValue);

      const formValues = {
        ...getFormFields(".review-write-modal__form", ".input-transparent"),
        product: productId,
        rating,
      };

      const status = validation(sendReviewButton);

      if (status) {
        if (rating) {
          await sendReview(formValues);
        } else {
          bad_modal("Додайте вашу оцінку!");
        }
      }
    }
  });
}
