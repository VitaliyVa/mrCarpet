import { instance } from "./instance";
import {
  showLoader,
  accept_modal,
  bad_modal,
} from "../components/module/form_action";

export const loginUser = async (values) => {
  showLoader();

  try {
    const { data } = await instance.post("/users/user_login/", values);

    accept_modal();
    window.location.reload();

    return data;
  } catch ({ response }) {
    bad_modal(response.data.message);
  }
};

export const registerUser = async (values) => {
  showLoader();

  try {
    const { data } = await instance.post("/users/register/", values);

    accept_modal();
    window.location.reload();

    return data;
  } catch ({ response }) {
    bad_modal(response.data.message);
  }
};
