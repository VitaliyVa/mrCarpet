import { instance } from "./instance";
import { accept_modal, bad_modal } from "../components/module/form_action";

export const addToFavorite = async (productId, onSucces) => {
  try {
    const { data } = await instance.post("/favourite-products/", {
      product: productId,
    });

    if (onSucces) {
      onSucces();
    }

    accept_modal(data?.message);

    return data;
  } catch ({ response }) {
    bad_modal(response?.data?.message);
  }
};

export const removeFromFavorite = async (productId, onSucces) => {
  try {
    const { data } = await instance.delete(`/favourite-products/${productId}`);

    if (onSucces) {
      onSucces();
    }

    accept_modal(data?.message);

    return data;
  } catch ({ response }) {
    bad_modal(response?.data?.message);
  }
};
