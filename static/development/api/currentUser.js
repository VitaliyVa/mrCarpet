import { instance } from "./instance";
import {
  showLoader,
  accept_modal,
  bad_modal,
} from "../components/module/form_action";

export const updateCurrentUser = async (values) => {
  showLoader();

  try {
    const { data } = await instance.patch("/users/update_profile/", values);

    accept_modal();
    window.location.reload();

    return data;
  } catch ({ response }) {
    bad_modal(response?.data?.message);
  }
};
