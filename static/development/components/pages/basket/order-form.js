import axios from "axios";
import Cookies from "js-cookie";
import { getNovaPostData } from "./nova-post";
import { showSuccess, showError } from "./notification";

function getScrollTarget(field) {
  if (!field) return null;

  if (field.id === "nova-post-warehouse-select") {
    return (
      field.closest(".nova-post-warehouse-wrapper") ||
      field.closest(".choices") ||
      field
    );
  }

  return field.closest(".nova-post-city-wrapper") || field;
}

function scrollToField(field) {
  const target = getScrollTarget(field);
  if (!target) return;

  const headerOffset = 80;
  const top =
    target.getBoundingClientRect().top + window.pageYOffset - headerOffset;

  window.scrollTo({
    top: Math.max(0, top),
    behavior: "smooth",
  });

  // focus після короткої затримки, щоб не зривати smooth scroll
  window.setTimeout(() => {
    if (field.id === "nova-post-warehouse-select") {
      const choicesInner = target.querySelector(".choices__inner");
      if (choicesInner) {
        choicesInner.focus?.();
      }
      return;
    }

    if (typeof field.focus === "function") {
      field.focus({ preventScroll: true });
    }
  }, 350);
}

function isValidEmail(value) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

// Валідація форми замовлення (порядок = зверху вниз у DOM)
function validateOrderForm() {
  const nameInput = document.getElementById("nova-post-name");
  const emailInput = document.getElementById("nova-post-email");
  const phoneInput = document.getElementById("nova-post-phone");
  const cityInput = document.getElementById("nova-post-city-input");
  const warehouseSelect = document.getElementById("nova-post-warehouse-select");

  clearFieldError(cityInput);
  clearFieldError(warehouseSelect);
  clearFieldError(nameInput);
  clearFieldError(emailInput);
  clearFieldError(phoneInput);

  const checks = [
    {
      field: cityInput,
      invalid: () => !cityInput?.value.trim(),
      message: "Будь ласка, оберіть місто",
    },
    {
      field: warehouseSelect,
      invalid: () => !warehouseSelect?.value,
      message: "Будь ласка, оберіть відділення",
    },
    {
      field: nameInput,
      invalid: () => !nameInput?.value.trim(),
      message: "Будь ласка, введіть ваше ім'я",
    },
    {
      field: emailInput,
      invalid: () => !isValidEmail(emailInput?.value.trim() || ""),
      message: "Будь ласка, введіть коректний email",
    },
    {
      field: phoneInput,
      invalid: () => {
        const phoneValue = phoneInput?.value.replace(/\D/g, "") || "";
        return phoneValue.length < 12;
      },
      message: "Будь ласка, введіть коректний номер телефону",
    },
  ];

  let firstInvalid = null;

  checks.forEach(({ field, invalid, message }) => {
    if (!field || !invalid()) return;
    setFieldError(field, message);
    if (!firstInvalid) {
      firstInvalid = field;
    }
  });

  if (firstInvalid) {
    scrollToField(firstInvalid);
    return false;
  }

  return true;
}

// Встановлення помилки для поля
function setFieldError(field, message) {
  if (!field) return;

  field.classList.add("input-error");

  const container =
    field.closest(".nova-post-warehouse-wrapper") ||
    field.closest(".nova-post-city-wrapper") ||
    field.parentElement;

  if (field.id === "nova-post-warehouse-select") {
    container?.querySelector(".choices")?.classList.add("input-error");
  }

  let errorMsg = container.querySelector(".error-message");
  if (!errorMsg) {
    errorMsg = document.createElement("div");
    errorMsg.className = "error-message";
    container.appendChild(errorMsg);
  }
  errorMsg.textContent = message;

  setTimeout(() => {
    clearFieldError(field);
  }, 10000);
}

// Очищення помилки для поля
function clearFieldError(field) {
  if (!field) return;

  field.classList.remove("input-error");

  const container =
    field.closest(".nova-post-warehouse-wrapper") ||
    field.closest(".nova-post-city-wrapper") ||
    field.parentElement;

  container?.querySelector(".choices")?.classList.remove("input-error");

  const errorMsg = container?.querySelector(".error-message");
  if (errorMsg) {
    errorMsg.remove();
  }
}

// Функція для капіталізації першої літери
function capitalizeFirstLetter(str) {
  if (!str) return str;
  return str.charAt(0).toUpperCase() + str.slice(1);
}

// Перевірка порожньої корзини (використовуємо дані з Django)
export function checkEmptyCart() {
  const cartProductsCount = window.cartProductsCount || 0;
  const emptyCartBlock = document.getElementById("empty-cart-block");
  const checkoutContent = document.getElementById("checkout-content");
  const cartCount = document.getElementById("cart-count");
  
  if (cartProductsCount === 0) {
    // Показуємо блок порожньої корзини
    if (emptyCartBlock) {
      emptyCartBlock.style.display = "flex";
    }
    // Ховаємо контент checkout
    if (checkoutContent) {
      checkoutContent.style.display = "none";
    }
    // Оновлюємо лічильник
    if (cartCount) {
      cartCount.textContent = "0 товарів";
    }
  } else {
    // Ховаємо блок порожньої корзини
    if (emptyCartBlock) {
      emptyCartBlock.style.display = "none";
    }
    // Показуємо контент checkout
    if (checkoutContent) {
      checkoutContent.style.display = "flex";
    }
  }
}

// Отримання товарів з кошика для замовлення
async function getCartProducts() {
  try {
    const response = await axios.get("/api/cart-products/", {
      headers: {
        "X-CSRFToken": Cookies.get("csrftoken"),
      },
    });
    return response.data || [];
  } catch (error) {
    console.error("Помилка при отриманні товарів з кошика:", error);
    return [];
  }
}

// Відправка замовлення
export async function submitOrder() {
  // Валідація форми
  if (!validateOrderForm()) {
    return;
  }

  const nameInput = document.getElementById("nova-post-name");
  const emailInput = document.getElementById("nova-post-email");
  const phoneInput = document.getElementById("nova-post-phone");
  const cityInput = document.getElementById("nova-post-city-input");

  // Card radio is disabled while LiqPay is test-only — fall back to cash
  const paymentMethod =
    document.querySelector('input[name="payment"]:checked:not(:disabled)') ||
    document.getElementById("cash");

  if (!paymentMethod) {
    showError("Будь ласка, оберіть спосіб оплати");
    return;
  }

  const novaPostData = getNovaPostData();

  const fullName = nameInput.value.trim().split(" ");
  const firstName = fullName[0] || "";
  const lastName = fullName.slice(1).join(" ") || "";

  const warehouseTitle = novaPostData.warehouse?.title || "";
  const cityName = capitalizeFirstLetter(cityInput.value.trim());
  // address = відділення (або місто, якщо відділення ще не обрано).
  // Місто окремо в city — не дублюємо «Ланівці, Ланівці» в листах.
  const address = warehouseTitle || cityName;

  let paymentType = "cash";
  if (paymentMethod.id === "card") {
    paymentType = "liqpay";
  } else if (paymentMethod.id === "cash") {
    paymentType = "cash";
  }

  const orderData = {
    name: firstName,
    surname: lastName || firstName,
    email: emailInput.value.trim(),
    phone: phoneInput.value.trim(),
    city: cityName,
    address: address,
    payment_type: paymentType,
    promocode: localStorage.getItem("applied_promocode") || "",
  };

  // Показуємо індикатор завантаження
  const submitBtn = document.querySelector(".basket__to-order-btn");
  const originalBtnContent = submitBtn.innerHTML;
  submitBtn.innerHTML = '<span class="btn-gold">Обробка замовлення...</span>';
  submitBtn.disabled = true;

  try {
    // Відправляємо запит через axios на правильний endpoint
    const response = await axios.post("/api/create-order/", orderData, {
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": Cookies.get("csrftoken"),
      },
    });

    // Обробляємо успішну відповідь
    console.log("Відповідь від сервера:", response.data);
    console.log("Payment type:", orderData.payment_type);
    
    if (response.status === 200 || response.status === 201 || response.data?.success) {
      // Очищаємо промокод з localStorage
      localStorage.removeItem("applied_promocode");
      // purchase: лише на /success/ (session + order status gate) — без double-fire

      // Визначаємо куди перенаправляти на основі payment_type або redirect_url
      let redirectUrl = null;
      
      // Спочатку перевіряємо redirect_url з відповіді сервера
      if (response.data?.redirect_url) {
        redirectUrl = response.data.redirect_url;
        console.log("Використовуємо redirect_url з відповіді:", redirectUrl);
      } 
      // Якщо немає redirect_url, перевіряємо payment_type
      else if (orderData.payment_type === "liqpay") {
        redirectUrl = "/payment/";
        console.log("Payment type = liqpay, перенаправляємо на /payment/");
      }
      // Для готівкової оплати перенаправляємо на success
      else {
        redirectUrl = "/success/";
        console.log("Payment type = cash, перенаправляємо на /success/");
      }
      
      // Перенаправляємо одразу
      if (redirectUrl) {
        console.log("Перенаправляємо на:", redirectUrl);
        window.location.href = redirectUrl;
        return;
      } else {
        console.error("Не вдалося визначити URL для перенаправлення");
      }
    }
  } catch (error) {
    console.error("Помилка при оформленні замовлення:", error);
    
    // Обробляємо помилки валідації від сервера
    if (error.response && error.response.data) {
      const serverErrors = error.response.data;
      
      // Показуємо помилки від сервера
      if (serverErrors.name) {
        setFieldError(nameInput, serverErrors.name[0] || serverErrors.name);
      }
      if (serverErrors.email) {
        setFieldError(emailInput, serverErrors.email[0] || serverErrors.email);
        scrollToField(emailInput);
      }
      if (serverErrors.phone) {
        setFieldError(phoneInput, serverErrors.phone[0] || serverErrors.phone);
      }
      if (serverErrors.city) {
        setFieldError(cityInput, serverErrors.city[0] || serverErrors.city);
      }

      if (serverErrors.message) {
        showError(serverErrors.message);
      } else if (serverErrors.error || serverErrors.detail) {
        showError(serverErrors.error || serverErrors.detail);
      }
    } else {
      showError("Виникла помилка при оформленні замовлення. Спробуйте ще раз.");
    }
    
    // Повертаємо кнопку в початковий стан
    submitBtn.innerHTML = originalBtnContent;
    submitBtn.disabled = false;
  }
}

// Ініціалізація обробника для кнопки замовлення
export function initOrderForm() {
  const submitBtn = document.querySelector(".basket__to-order-btn");
  
  if (submitBtn) {
    submitBtn.addEventListener("click", (e) => {
      e.preventDefault();
      submitOrder();
    });
  }
}

