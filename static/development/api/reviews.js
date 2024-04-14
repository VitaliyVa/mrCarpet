import { instance } from "./instance";
import {
  showLoader,
  accept_modal,
  bad_modal,
} from "../components/module/form_action";

export const sendReview = async (values) => {
  showLoader();

  try {
    const { data } = await instance.post("/product-reviews/", values);

    accept_modal(data?.message || "Ваш відгук успішно відправлено 🎉🎉🎉");
    window.location.reload();

    return data;
  } catch ({ response }) {
    bad_modal(response?.data?.message || "Упс... щось пішло не так🥲");
  }
};
