import axios from "axios";
import Cookies from "js-cookie";
import { getNovaPostData } from "./nova-post";
import { showSuccess, showError } from "./notification";

// Валідація форми замовлення
function validateOrderForm() {
  const errors = [];
  let hasErrors = false;

  // Отримуємо всі необхідні поля
  const nameInput = document.getElementById("nova-post-name");
  const phoneInput = document.getElementById("nova-post-phone");
  const cityInput = document.getElementById("nova-post-city-input");
  const warehouseSelect = document.getElementById("nova-post-warehouse-select");

  // Очищаємо попередні помилки
  clearFieldError(nameInput);
  clearFieldError(phoneInput);
  clearFieldError(cityInput);
  clearFieldError(warehouseSelect);

  // Перевірка імені
  if (!nameInput.value.trim()) {
    setFieldError(nameInput, "Будь ласка, введіть ваше ім'я");
    errors.push("name");
    hasErrors = true;
  }

  // Перевірка телефону
  const phoneValue = phoneInput.value.replace(/\D/g, ""); // Видаляємо всі нецифрові символи
  if (!phoneValue || phoneValue.length < 12) {
    setFieldError(phoneInput, "Будь ласка, введіть коректний номер телефону");
    errors.push("phone");
    hasErrors = true;
  }

  // Перевірка міста
  if (!cityInput.value.trim()) {
    setFieldError(cityInput, "Будь ласка, оберіть місто");
    errors.push("city");
    hasErrors = true;
  }

  // Перевірка відділення
  if (!warehouseSelect.value) {
    setFieldError(warehouseSelect, "Будь ласка, оберіть відділення");
    errors.push("warehouse");
    hasErrors = true;
  }

  return !hasErrors;
}

// Встановлення помилки для поля
function setFieldError(field, message) {
  field.classList.add("input-error");
  
  // Перевіряємо чи вже є повідомлення про помилку
  let errorMsg = field.parentElement.querySelector(".error-message");
  if (!errorMsg) {
    errorMsg = document.createElement("div");
    errorMsg.className = "error-message";
    field.parentElement.appendChild(errorMsg);
  }
  errorMsg.textContent = message;

  // Автоматично прибираємо помилку через 10 секунд
  setTimeout(() => {
    clearFieldError(field);
  }, 10000);
}

// Очищення помилки для поля
function clearFieldError(field) {
  field.classList.remove("input-error");
  const errorMsg = field.parentElement.querySelector(".error-message");
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
  const phoneInput = document.getElementById("nova-post-phone");
  const cityInput = document.getElementById("nova-post-city-input");
  
  // Отримуємо обраний спосіб оплати
  const paymentMethod = document.querySelector('input[name="payment"]:checked');
  
  // Перевіряємо, чи обрано спосіб оплати
  if (!paymentMethod) {
    showError("Будь ласка, оберіть спосіб оплати");
    return;
  }
  
  // Отримуємо дані Нової Пошти
  const novaPostData = getNovaPostData();

  // Отримуємо товари з кошика
  const cartProducts = await getCartProducts();
  
  // Формуємо масив товарів для замовлення
  const products = cartProducts.map(item => ({
    product_attr_id: item.product_attr,
    quantity: item.quantity,
  }));

  // Розділяємо ім'я на name та surname
  const fullName = nameInput.value.trim().split(" ");
  const firstName = fullName[0] || "";
  const lastName = fullName.slice(1).join(" ") || "";
  
  // Формуємо адресу з даних Нової Пошти
  const warehouseTitle = novaPostData.warehouse?.title || "";
  const cityName = capitalizeFirstLetter(cityInput.value.trim());
  const address = warehouseTitle ? `${cityName}, ${warehouseTitle}` : cityName;

  // Визначаємо payment_type на основі обраного способу оплати
  let paymentType = "cash"; // Значення за замовчуванням
  if (paymentMethod.id === "card") {
    paymentType = "liqpay";
  } else if (paymentMethod.id === "cash") {
    paymentType = "cash";
  }

  // Формуємо дані для відправки
  const orderData = {
    name: firstName,
    surname: lastName || firstName, // Якщо прізвище не вказано, використовуємо ім'я
    phone: phoneInput.value.trim(),
    address: address,
    payment_type: paymentType, // Обов'язкове поле
    // Додаємо промокод якщо він був застосований
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
      if (serverErrors.phone) {
        setFieldError(phoneInput, serverErrors.phone[0] || serverErrors.phone);
      }
      if (serverErrors.city) {
        setFieldError(cityInput, serverErrors.city[0] || serverErrors.city);
      }
      
      // Загальна помилка
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

