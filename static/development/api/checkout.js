import { instance } from "./instance";
import {
  showLoader,
  accept_modal,
  bad_modal,
} from "../components/module/form_action";

export const createOrder = async (values) => {
  try {
    showLoader();

    const { data } = await instance.post(`/create-order/`, values);

    console.log(data);

    accept_modal("Ваше Замовлення прийнято!");

    return data;
  } catch ({ response }) {
    bad_modal(response?.data?.message);
  }
};
