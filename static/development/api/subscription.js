import { instance } from "./instance";
import {
  showLoader,
  accept_modal,
  bad_modal,
} from "../components/module/form_action";

export const subscribeToNewsletter = async (email) => {
  try {
    showLoader();

    const { data } = await instance.post("/subscription/", {
      email,
    });

    accept_modal(
      data?.message ||
        "Ви успішно підписалися на розсилку новин та акцій 🎉🎉🎉"
    );

    return data;
  } catch ({ response }) {
    bad_modal(response?.data?.message || "Упс... щось пішло не так🥲");
  }
};
