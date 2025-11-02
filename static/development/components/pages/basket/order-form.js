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
  
  // Отримуємо дані Нової Пошти
  const novaPostData = getNovaPostData();

  // Отримуємо товари з кошика
  const cartProducts = await getCartProducts();
  
  // Формуємо масив товарів для замовлення
  const products = cartProducts.map(item => ({
    product_attr_id: item.product_attr,
    quantity: item.quantity,
  }));

  // Формуємо дані для відправки
  const orderData = {
    name: nameInput.value.trim(),
    phone: phoneInput.value.trim(),
    city: capitalizeFirstLetter(cityInput.value.trim()), // Капіталізуємо першу літеру
    settlement_ref: novaPostData.settlement?.ref || "",
    warehouse_ref: novaPostData.warehouse?.ref || "",
    warehouse_title: novaPostData.warehouse?.title || "",
    payment_method: paymentMethod?.id || "cash",
    // Додаємо промокод якщо він був застосований
    promocode: localStorage.getItem("applied_promocode") || "",
    // Додаємо товари
    products: products,
  };

  // Показуємо індикатор завантаження
  const submitBtn = document.querySelector(".basket__to-order-btn");
  const originalBtnContent = submitBtn.innerHTML;
  submitBtn.innerHTML = '<span class="btn-gold">Обробка замовлення...</span>';
  submitBtn.disabled = true;

  try {
    // Відправляємо запит через axios
    const response = await axios.post("/api/orders/", orderData, {
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": Cookies.get("csrftoken"),
      },
    });

    // Обробляємо успішну відповідь
      if (response.data.success || response.status === 200 || response.status === 201) {
      // Очищаємо промокод з localStorage
      localStorage.removeItem("applied_promocode");
      
      // Перенаправляємо на сторінку успіху або показуємо повідомлення
      if (response.data.redirect_url) {
        window.location.href = response.data.redirect_url;
      } else {
        showSuccess("Замовлення успішно оформлено!");
        // Перенаправляємо через 2 секунди
        setTimeout(() => {
          window.location.href = "/";
        }, 2000);
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
      if (serverErrors.error || serverErrors.detail) {
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

