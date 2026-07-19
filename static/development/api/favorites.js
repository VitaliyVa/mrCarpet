import { instance } from "./instance";
import { showSuccess, showError } from "../utils/notifications";
import { updateCountBadge } from "../utils/updateCountBadge";
import { trackEcommerce, CURRENCY } from "../utils/analytics";

export const addToFavorite = async (productId, onSucces, analyticsMeta) => {
  try {
    const { data } = await instance.post("/favourite-products/", {
      product: productId,
    });

    showSuccess(data?.message || "Додано в обране!");

    const quantity = data?.favourite?.quantity ?? data?.quantity ?? 0;
    updateCountBadge(".header_bottom_panel_like", quantity);

    const item = analyticsMeta || {
      item_id: String(productId),
      item_brand: "mr.Carpet",
      quantity: 1,
    };
    if (item.item_id) {
      trackEcommerce("add_to_wishlist", {
        currency: CURRENCY,
        items: [item],
      });
    }

    if (onSucces) {
      onSucces();
    }

    return data;
  } catch ({ response }) {
    showError(response?.data?.message || "Помилка");
  }
};

export const removeFromFavorite = async (productId, onSucces, analyticsMeta) => {
  try {
    const { data } = await instance.delete(`/favourite-products/${productId}/`);

    if (onSucces) {
      onSucces();
    }

    showSuccess(data?.message || "Товар видалено з обраного!");

    const quantity = data?.quantity ?? data?.favourite?.quantity ?? 0;
    updateCountBadge(".header_bottom_panel_like", quantity);

    const item = analyticsMeta || {
      item_id: String(productId),
      item_brand: "mr.Carpet",
      quantity: 1,
    };
    if (item.item_id) {
      trackEcommerce("remove_from_wishlist", {
        currency: CURRENCY,
        items: [item],
      });
    }

    return data;
  } catch ({ response }) {
    showError(response?.data?.message || "Помилка");
  }
};
