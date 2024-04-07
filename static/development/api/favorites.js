import { instance } from "./instance";
import { accept_modal, bad_modal } from "../components/module/form_action";
import { updateCountBadge } from "../utils/updateCountBadge";

export const addToFavorite = async (productId, onSucces) => {
  try {
    const { data } = await instance.post("/favourite-products/", {
      product: productId,
    });

    if (onSucces) {
      onSucces();
    }

    accept_modal(data?.message);

    // updateCountBadge(
    //   ".header_bottom_panel_like",
    //   data?.favourite_products?.length
    // );

    return data;
  } catch ({ response }) {
    bad_modal(response?.data?.message || "Товар додано!");
  }
};

export const removeFromFavorite = async (productId, onSucces) => {
  try {
    const { data } = await instance.delete(`/favourite-products/${productId}`);

    if (onSucces) {
      onSucces();
    }

    accept_modal(data?.message || "Товар видалено!");

    // updateCountBadge(
    //   ".header_bottom_panel_like",
    //   data?.favourite_products?.length
    // );

    return data;
  } catch ({ response }) {
    bad_modal(response?.data?.message);
  }
};
