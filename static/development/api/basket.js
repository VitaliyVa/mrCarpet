import { instance } from "./instance";
import { accept_modal, bad_modal } from "../components/module/form_action";
import { updateCountBadge } from "../utils/updateCountBadge";

export const addToBasket = async (product, onSucces) => {
  try {
    const { data } = await instance.post("/cart-products/", product);

    if (onSucces) {
      onSucces();
    }

    accept_modal(data?.message || "Додано в корзину!");

    updateCountBadge(".header_bottom_panel_cart", data?.cart_products?.length);

    return data;
  } catch ({ response }) {
    bad_modal(response?.data?.message);
  }
};
