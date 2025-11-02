import { instance } from "./instance";
import { showSuccess, showError } from "../utils/notifications";
import { updateCountBadge } from "../utils/updateCountBadge";

export const addToFavorite = async (productId, onSucces) => {
  try {
    const { data } = await instance.post("/favourite-products/", {
      product: productId,
    });

    if (onSucces) {
      onSucces();
    }

    showSuccess(data?.message || "Додано в обране!");

    updateCountBadge(".header_bottom_panel_like", data?.favourite?.quantity);

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

    showSuccess(data?.message || "Товар видалено!");

    updateCountBadge(".header_bottom_panel_like", data?.favourite?.quantity);

    return data;
  } catch ({ response }) {
    showError(response?.data?.message || "Помилка");
  }
};
