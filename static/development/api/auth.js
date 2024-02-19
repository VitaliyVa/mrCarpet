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

    return data;
  } catch (error) {
    console.log(error);
    bad_modal();
  }
};

export const registerUser = async (values) => {
  showLoader();

  try {
    const { data } = await instance.post("/users/register/", values);
    accept_modal();

    return data;
  } catch (error) {
    console.log(error);
    bad_modal();
  }
};
