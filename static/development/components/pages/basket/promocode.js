import "./promocode.scss";
import { instance } from "../../../api/instance";
import { showSuccess, showError } from "./notification";

// Функціональність для промокоду
export function initPromocode() {
  console.log("initPromocode called"); // Логування
  
  document.addEventListener("click", ({ target }) => {
    console.log("Click event triggered", target); // Логування
    
    const promocodeButton = target.closest(".basket__promocode-add-btn");
    console.log("Promocode button found:", promocodeButton); // Логування
    
    if (promocodeButton) {
      console.log("Promocode button clicked!"); // Логування
      
      const promocodeInput = document.querySelector(".basket__promocode input");
      const promocode = promocodeInput.value.trim();
      
      console.log("Promocode value:", promocode); // Логування
      
      if (!promocode) {
        showError("Будь ласка, введіть промокод");
        return;
      }
      
      // Показуємо індикатор завантаження
      promocodeButton.textContent = "Перевіряємо...";
      promocodeButton.disabled = true;
      
      console.log("Sending request to /api/check-promocode/"); // Логування
      
      // Відправляємо запит на перевірку промокоду
      instance.post("/check-promocode/", { promocode })
        .then(({ data }) => {
          console.log("Response received:", data); // Логування
          
          if (data.success) {
            // Оновлюємо ціни на сторінці
            updatePricesWithDiscount(data);
            
            // Показуємо повідомлення про успіх
            showSuccess(data.message || "Промокод успішно застосовано!");
            
            // Зберігаємо промокод в localStorage для подальшого використання
            localStorage.setItem('applied_promocode', promocode);
            
            // Змінюємо вигляд кнопки
            promocodeButton.textContent = "Застосовано";
            promocodeButton.classList.add("applied");
          }
        })
        .catch(({ response }) => {
          console.log("Error occurred:", response); // Логування
          
          // Показуємо повідомлення про помилку
          const errorMessage = response?.data?.error || "Помилка при перевірці промокоду";
          showError(errorMessage);
          
          // Повертаємо кнопку в початковий стан
          promocodeButton.textContent = "Додати";
          promocodeButton.disabled = false;
        });
    }
  });
}

// Функція для оновлення цін зі знижкою
function updatePricesWithDiscount(data) {
  const { final_price, discount_percent, free_shipping } = data;

  // Оновлюємо загальну ціну товарів
  const totalPriceElements = document.querySelectorAll(
    ".basket__calculate-sum-products-cost, .basket__calculate-total-price-value"
  );
  totalPriceElements.forEach((element) => {
    element.textContent = `${final_price} грн.`;
  });

  // Додаємо інформацію про знижку
  const calculateBlock = document.querySelector(".basket__calculate");
  if (calculateBlock) {
    let discountBlock = calculateBlock.querySelector(
      ".basket__calculate-discount"
    );

    if (!discountBlock) {
      discountBlock = document.createElement("div");
      discountBlock.className = "basket__calculate-discount basket_right_block";
      discountBlock.innerHTML = `
        <p class="basket__calculate-discount-title">Знижка</p>
        <p class="basket__calculate-discount-value color_gold">-${discount_percent}%</p>
      `;

      const sumProductsBlock = calculateBlock.querySelector(
        ".basket__calculate-sum-products"
      );
      sumProductsBlock.after(discountBlock);
    } else {
      discountBlock.querySelector(
        ".basket__calculate-discount-value"
      ).textContent = `-${discount_percent}%`;
    }
  }

  updateFreeShippingUI(free_shipping || null, final_price);
}

function updateFreeShippingUI(fs, finalPrice) {
  const root = document.getElementById("basket-delivery-cost");
  const priceEl = document.getElementById("basket-delivery-price");
  const hintEl = document.getElementById("basket-delivery-hint");
  if (!root || !priceEl) return;

  const enabled =
    fs?.enabled ?? root.dataset.fsEnabled === "1";
  const threshold = Number(fs?.threshold ?? root.dataset.fsThreshold ?? 0);
  const fromPrice = Number(fs?.delivery_from_price ?? root.dataset.fsFrom ?? 90);
  const total = Number(finalPrice);
  const qualifies =
    fs?.qualifies ?? (enabled && threshold > 0 && total >= threshold);
  const remaining =
    fs?.remaining ??
    (enabled && !qualifies ? Math.max(0, threshold - Math.round(total)) : 0);

  root.dataset.fsEnabled = enabled ? "1" : "0";
  root.dataset.fsThreshold = String(threshold);
  root.dataset.fsFrom = String(fromPrice);

  if (qualifies) {
    priceEl.classList.add("is-free");
    priceEl.innerHTML = `
      <span class="basket__calculate-delivery-was">Від ${fromPrice} грн.</span>
      <span class="basket__calculate-delivery-now">Безкоштовно</span>
    `;
    if (hintEl) {
      hintEl.hidden = false;
      hintEl.classList.add("is-free");
      hintEl.textContent = `Безкоштовна доставка від ${threshold} грн.`;
    }
  } else {
    priceEl.classList.remove("is-free");
    priceEl.innerHTML = `
      <span class="basket__calculate-delivery-carrier">за тарифами<br />перевізника</span>
    `;
    if (hintEl) {
      if (enabled && remaining > 0) {
        hintEl.hidden = false;
        hintEl.classList.remove("is-free");
        hintEl.textContent = `До безкоштовної доставки ще ${remaining} грн.`;
      } else {
        hintEl.hidden = true;
        hintEl.textContent = "";
      }
    }
  }

  const npPrice = document.getElementById("nova-post-delivery-price");
  if (npPrice) {
    if (qualifies) {
      npPrice.classList.add("is-free");
      npPrice.innerHTML = `
        <span class="basket__checkbox-item-price-was">Від ${fromPrice} грн.</span>
        <span class="basket__checkbox-item-price-now">Безкоштовно</span>
      `;
    } else {
      npPrice.classList.remove("is-free");
      npPrice.textContent = `Від ${fromPrice} грн.`;
    }
  }
}

// Функція для відновлення застосованого промокоду при завантаженні сторінки
export function restorePromocode() {
  const appliedPromocode = localStorage.getItem('applied_promocode');
  if (appliedPromocode) {
    // Відновлюємо стан кнопки
    const promocodeButton = document.querySelector(".basket__promocode-add-btn");
    if (promocodeButton) {
      promocodeButton.textContent = "Застосовано";
      promocodeButton.classList.add("applied");
    }
    
    // Відновлюємо промокод в полі вводу
    const promocodeInput = document.querySelector(".basket__promocode input");
    if (promocodeInput) {
      promocodeInput.value = appliedPromocode;
    }
  }
} 