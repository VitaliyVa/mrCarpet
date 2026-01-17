import { instance } from "./instance";
import { showSuccess, showError } from "../utils/notifications";
import { updateCountBadge } from "../utils/updateCountBadge";

export const addToFavorite = async (productId, onSucces) => {
  try {
    const { data } = await instance.post("/favourite-products/", {
      product: productId,
    });

    showSuccess(data?.message || "Додано в обране!");

    // При create повертається {favourite: {...}, message: "..."}
    const quantity = data?.favourite?.quantity ?? data?.quantity ?? 0;
    updateCountBadge(".header_bottom_panel_like", quantity);

    if (onSucces) {
      onSucces();
    }

    return data;
  } catch ({ response }) {
    showError(response?.data?.message || "Помилка");
  }
};

export const removeFromFavorite = async (productId, onSucces) => {
  try {
    const { data } = await instance.delete(`/favourite-products/${productId}/`);

    if (onSucces) {
      onSucces();
    }

    showSuccess(data?.message || "Товар видалено з обраного!");

    // При destroy повертається FavouriteSerializer без обгортки favourite
    const quantity = data?.quantity ?? data?.favourite?.quantity ?? 0;
    updateCountBadge(".header_bottom_panel_like", quantity);

    return data;
  } catch ({ response }) {
    showError(response?.data?.message || "Помилка");
  }
};
