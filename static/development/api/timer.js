import { instance } from "./instance";
import {
  showLoader,
  accept_modal,
  bad_modal,
} from "../components/module/form_action";

// export const addPromocode = async (code) => {
//   try {
//     showLoader();
//     const { data } = await instance.post(`/add-promocode/`);

//     // updateCountBadge(".header_bottom_panel_cart", data?.quantity);
//     // updateBasket(data);

//     console.log(data);

//     return data;
//   } catch ({ response }) {
//     bad_modal(response?.data?.message);
//   }
// };
