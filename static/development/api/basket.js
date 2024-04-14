import { instance } from "./instance";
import {
  showLoader,
  accept_modal,
  bad_modal,
} from "../components/module/form_action";
import { updateCountBadge } from "../utils/updateCountBadge";
import { updateBasket } from "../components/pages/basket/utils/updateBasket";

export const addToBasket = async (product, onSucces) => {
  try {
    const { data } = await instance.post("/cart-products/", product);

    if (onSucces) {
      onSucces();
    }

    accept_modal(data?.message || "Додано в корзину!");

    updateCountBadge(".header_bottom_panel_cart", data?.quantity);
    updateBasket(data);

    return data;
  } catch ({ response }) {
    bad_modal(response?.data?.message);
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
    bad_modal(response?.data?.message);
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
    bad_modal(response?.data?.message);
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
