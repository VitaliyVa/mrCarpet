import { instance } from "./instance";
import { bad_modal } from "../components/module/form_action";

export const addToBasket = async (product) => {
  try {
    const { data } = await instance.post("/cart-products/", product);

    return data;
  } catch ({ response }) {
    bad_modal(response?.data?.message);
  }
};
