// Order Handler - обробка відправки замовлення
import { getNovaPostData } from "./nova-post";
import { showError, showSuccess } from "../../../utils/notifications";

export function initOrderHandler() {
  const orderBtn = document.querySelector(".basket__to-order-btn");
  const orderLink = orderBtn?.querySelector(".btn-gold");

  if (!orderBtn || !orderLink) {
    return;
  }

  // Перехоплюємо клік на кнопці
  orderLink.addEventListener("click", function (e) {
    e.preventDefault();

    // Збираємо дані з форми
    const orderData = collectOrderData();

    if (!orderData) {
      showError("Будь ласка, заповніть всі обов'язкові поля");
      return;
    }

    // Відправляємо дані на сервер
    submitOrder(orderData);
  });
}

// Збір даних замовлення
function collectOrderData() {
  // Перевіряємо який спосіб доставки обрано
  const deliveryMethod = document.querySelector('input[name="delivery"]:checked');
  
  if (!deliveryMethod) {
    showError("Будь ласка, оберіть спосіб доставки");
    return null;
  }

  const deliveryType = deliveryMethod.id; // nova-post, urk-post, justin, courier

  // Перевіряємо спосіб оплати
  const paymentMethod = document.querySelector('input[name="payment"]:checked');
  
  if (!paymentMethod) {
    showError("Будь ласка, оберіть спосіб оплати");
    return null;
  }

  const paymentType = paymentMethod.id; // cash або card

  let orderData = {
    payment_type: paymentType === "cash" ? "cash" : "liqpay",
  };

  // Збираємо дані в залежності від способу доставки
  if (deliveryType === "nova-post") {
    const novaPostData = getNovaPostData();
    const nameInput = document.getElementById("nova-post-name");
    const phoneInput = document.getElementById("nova-post-phone");

    if (!novaPostData.settlement || !novaPostData.warehouse) {
      showError("Будь ласка, оберіть місто та відділення Нової Пошти");
      return null;
    }

    if (!nameInput?.value || !phoneInput?.value) {
      showError("Будь ласка, заповніть ім'я та телефон");
      return null;
    }

    // Розбиваємо ім'я на ім'я та прізвище (якщо є пробіл)
    const fullName = nameInput.value.trim();
    const nameParts = fullName.split(" ");
    const firstName = nameParts[0] || "";
    const lastName = nameParts.slice(1).join(" ") || firstName;

    orderData = {
      ...orderData,
      name: firstName,
      surname: lastName,
      phone: phoneInput.value.trim(),
      email: "", // Якщо потрібно, додайте поле для email
      address: `Нова Пошта: ${novaPostData.settlement.title}, ${novaPostData.warehouse.title}`,
      message: `Settlement ID: ${novaPostData.settlement.id}, Settlement Ref: ${novaPostData.settlement.ref}, Warehouse ID: ${novaPostData.warehouse.id}, Warehouse Ref: ${novaPostData.warehouse.ref}`,
    };
  }
  // Тут можна додати обробку інших способів доставки
  else {
    showError("Цей спосіб доставки поки недоступний");
    return null;
  }

  return orderData;
}

// Відправка замовлення на сервер
async function submitOrder(orderData) {
  try {
    // Показуємо індикатор завантаження (якщо є)
    const loader = document.querySelector(".modal_loading__block");
    if (loader) {
      loader.classList.add("active");
    }

    // Отримуємо CSRF токен
    const csrfToken = getCookie("csrftoken");

    const response = await fetch("/api/create-order/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
      },
      body: JSON.stringify(orderData),
    });

    // Ховаємо індикатор завантаження
    if (loader) {
      loader.classList.remove("active");
    }

    if (response.ok) {
      const data = await response.json();
      
      // Якщо оплата через LiqPay, перенаправляємо на сторінку оплати
      if (orderData.payment_type === "liqpay") {
        window.location.href = "/payment/";
      } else {
        // Інакше перенаправляємо на сторінку успіху
        window.location.href = "/success/";
      }
    } else {
      const errorData = await response.json();
      showError(errorData.message || "Помилка при створенні замовлення");
    }
  } catch (error) {
    console.error("Помилка при відправці замовлення:", error);
    showError("Помилка при відправці замовлення. Спробуйте ще раз.");
    
    // Ховаємо індикатор завантаження
    const loader = document.querySelector(".modal_loading__block");
    if (loader) {
      loader.classList.remove("active");
    }
  }
}

// Отримання CSRF токена з cookies
function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== "") {
    const cookies = document.cookie.split(";");
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === name + "=") {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

