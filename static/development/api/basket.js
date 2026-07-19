import { instance } from "./instance";
import { showError, showSuccess } from "../utils/notifications";
import { updateCountBadge } from "../utils/updateCountBadge";
import { updateBasket } from "../components/pages/basket/utils/updateBasket";
import {
  trackEcommerce,
  itemFromProductEl,
  itemsValue,
  CURRENCY,
} from "../utils/analytics";

export const addToBasket = async (product, onSucces, analyticsMeta) => {
  try {
    const { data } = await instance.post("/cart-products/", product);

    if (onSucces) {
      onSucces();
    }

    updateCountBadge(".header_bottom_panel_cart", data?.quantity);
    updateBasket(data);

    const item =
      analyticsMeta ||
      (product?.analyticsItem
        ? product.analyticsItem
        : {
            item_id: String(product.product || ""),
            item_brand: "mr.Carpet",
            quantity: product.quantity || 1,
            price: 0,
          });
    if (item?.item_id) {
      const qty = item.quantity || product.quantity || 1;
      trackEcommerce("add_to_cart", {
        currency: CURRENCY,
        value: itemsValue([{ ...item, quantity: qty }]),
        items: [{ ...item, quantity: qty }],
      });
    }

    showSuccess(data?.message || "Товар додано в кошик");

    return data;
  } catch (error) {
    const errorMessage =
      error?.response?.data?.message ||
      error?.message ||
      "Помилка при додаванні в кошик";
    showError(errorMessage);

    return null;
  }
};

export const removeFromBasket = async (productId, onSucces, analyticsMeta) => {
  try {
    const { data } = await instance.delete(`/cart-products/${productId}/`);

    if (onSucces) {
      onSucces();
    }

    updateCountBadge(".header_bottom_panel_cart", data?.quantity);
    updateBasket(data);

    if (analyticsMeta?.item_id) {
      trackEcommerce("remove_from_cart", {
        currency: CURRENCY,
        value: itemsValue([analyticsMeta]),
        items: [analyticsMeta],
      });
    }

    return data;
  } catch (error) {
    const errorMessage =
      error?.response?.data?.message ||
      error?.message ||
      "Помилка при видаленні з кошика";
    showError(errorMessage);

    return null;
  }
};

export const updateBasketItem = async ({ id, ...product }, onSucces) => {
  try {
    const { data } = await instance.patch(`/cart-products/${id}/`, product);

    if (onSucces) {
      onSucces(data);
    }

    updateCountBadge(".header_bottom_panel_cart", data?.quantity);
    updateBasket(data);

    return data;
  } catch (error) {
    const errorMessage =
      error?.response?.data?.message ||
      error?.message ||
      "Помилка при оновленні кошика";
    showError(errorMessage);

    return null;
  }
};

export { itemFromProductEl };
