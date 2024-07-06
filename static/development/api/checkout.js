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

    setTimeout(() => {
      document.location.href = "/success";
    }, 500);

    return data;
  } catch ({ response }) {
    bad_modal(response?.data?.message);
  }
};

export async function getSettlements(value) {
  try {
    const { data } = await instance.get(`/offices/?q=${value}`);

    return data;
  } catch (error) {
    console.log(error);
  }
}

export async function getWarehouses(value) {
  try {
    const { data } = await instance.get(`/warehouses?q=${value}`);

    return data;
  } catch (error) {
    console.log(error);
  }
}
