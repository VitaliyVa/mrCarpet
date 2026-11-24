import { instance } from "./instance";
import { showLoader, hideLoader } from "../components/module/form_action";
import { showSuccess, showError } from "../utils/notifications";
import { trackEvent, trackFormError } from "../utils/analytics";

/** DRF error keys = field names (never the values). */
function errorFields(error) {
  const data = error?.response?.data;
  if (data && typeof data === "object" && !Array.isArray(data)) {
    const keys = Object.keys(data);
    if (keys.length) return keys;
  }
  return [error?.response ? `http_${error.response.status}` : "network"];
}

function extractErrorMessage(error, fallback = "Сталася помилка") {
  const data = error?.response?.data;
  if (!data) {
    if (error?.request) {
      return "Не вдалося з'єднатися з сервером. Перевірте інтернет-з'єднання.";
    }
    return fallback;
  }

  if (typeof data === "string") return data;
  if (data.message) return data.message;
  if (data.detail) return data.detail;
  if (data.error) return data.error;
  if (Array.isArray(data) && data.length) return data[0];

  // DRF field errors: { email: ["..."], password: ["..."] }
  const firstKey = Object.keys(data).find(
    (key) => Array.isArray(data[key]) && data[key].length
  );
  if (firstKey) return data[firstKey][0];

  return fallback;
}

function translateAuthMessage(message) {
  const map = {
    "User with this email already exists":
      "Користувач з таким email вже існує",
    "User with these credentials doesn't exist":
      "Користувача з такими даними не існує",
  };

  if (map[message]) return map[message];
  if (message.includes("User with these credentials")) {
    return "Користувача з такими даними не існує";
  }
  if (message.includes("credentials")) {
    return "Невірні дані для входу";
  }
  if (message.toLowerCase().includes("already exists")) {
    return "Користувач з таким email вже існує";
  }
  return message;
}

function closeAuthModal(selector) {
  const modal = document.querySelector(selector);
  const overlay = modal?.closest(".modal-overlay");
  modal?.classList.remove("active");
  overlay?.classList.remove("active");
  document.body.style.overflowY = "initial";
}

export const loginUser = async (values) => {
  showLoader();

  try {
    const { data } = await instance.post("/users/user_login/", values);

    hideLoader();
    trackEvent("login", { method: "email" }, { beforeUnload: true });
    closeAuthModal(".login-modal");
    window.location.reload();

    return data;
  } catch (error) {
    hideLoader();
    trackFormError("login", errorFields(error));
    showError(
      translateAuthMessage(extractErrorMessage(error, "Помилка авторизації"))
    );
  }
};

export const registerUser = async (values) => {
  showLoader();

  try {
    const { data } = await instance.post("/users/register/", values);

    hideLoader();
    trackEvent("sign_up", { method: "email" }, { beforeUnload: true });
    closeAuthModal(".register-modal");
    showSuccess("Реєстрація успішна!");
    setTimeout(() => window.location.reload(), 1200);

    return data;
  } catch (error) {
    hideLoader();
    trackFormError("register", errorFields(error));
    showError(
      translateAuthMessage(extractErrorMessage(error, "Помилка реєстрації"))
    );
  }
};
