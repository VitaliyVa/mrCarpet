import { instance } from "./instance";
import {
  showLoader,
  accept_modal,
  bad_modal,
} from "../components/module/form_action";
import { updateBasket } from "../components/pages/basket/utils/updateBasket";

export const addPromocode = async (code) => {
  try {
    showLoader();

    const { data } = await instance.post("/add-promocode/", {
      code,
    });

    if (data?.promocode_total_price) {
      updateBasket({ total_price: data.promocode_total_price });
    }

    accept_modal(data?.message || "Промокод додано");

    return data;
  } catch ({ response }) {
    bad_modal(response?.data?.message || "Введіть дійсний промокод!");
  }
};
