import axios from "axios";
import Cookies from "js-cookie";

export const csrf = Cookies.get("csrftoken");

export const instance = axios.create({
  headers: {
    "X-CSRFToken": csrf,
  },
  baseURL: "/api",
});
