import { instance } from "./instance";
import { bad_modal } from "../components/module/form_action";

export const addToFavorite = async (productId) => {
  try {
    const { data } = await instance.post("/favourite-products/", {
      product: productId,
    });

    return data;
  } catch ({ response }) {
    bad_modal(response?.data?.message);
  }
};
