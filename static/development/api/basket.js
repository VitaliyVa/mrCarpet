import { instance } from "./instance";
import { showLoader } from "../components/module/form_action";
import { showSuccess, showError } from "../utils/notifications";
import { updateCountBadge } from "../utils/updateCountBadge";
import { updateBasket } from "../components/pages/basket/utils/updateBasket";

export const addToBasket = async (product, onSucces) => {
  try {
    const { data } = await instance.post("/cart-products/", product);

    if (onSucces) {
      onSucces();
    }

    showSuccess(data?.message || "Додано в корзину!");

    updateCountBadge(".header_bottom_panel_cart", data?.quantity);
    updateBasket(data);

    return data;
  } catch ({ response }) {
    showError(response?.data?.message || "Помилка при додаванні в кошик");
  }
};

export const removeFromBasket = async (productId, onSucces) => {
  try {
    const { data } = await instance.delete(`/cart-products/${productId}/`);

    if (onSucces) {
      onSucces();
    }

    updateCountBadge(".header_bottom_panel_cart", data?.quantity);
    updateBasket(data);

    return data;
  } catch ({ response }) {
    showError(response?.data?.message || "Помилка при додаванні в кошик");
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
  } catch ({ response }) {
    showError(response?.data?.message || "Помилка при додаванні в кошик");
  }
};

// export const addPromocode = async (code) => {
//   try {
//     showLoader();
//     const { data } = await instance.post(`/add-promocode/`);

//     // updateCountBadge(".header_bottom_panel_cart", data?.quantity);
//     // updateBasket(data);

//     console.log(data);

//     return data;
//   } catch ({ response }) {
//     bad_modal(response?.data?.message);
//   }
// };
