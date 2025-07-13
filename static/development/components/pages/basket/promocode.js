import "./promocode.scss";
import { instance } from "../../../api/instance";

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
        alert("Введіть промокод");
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
            alert(data.message);
            
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
          alert(errorMessage);
          
          // Повертаємо кнопку в початковий стан
          promocodeButton.textContent = "Додати";
          promocodeButton.disabled = false;
        });
    }
  });
}

// Функція для оновлення цін зі знижкою
function updatePricesWithDiscount(data) {
  const { original_price, final_price, discount_percent } = data;
  
  // Оновлюємо загальну ціну товарів
  const totalPriceElements = document.querySelectorAll(".basket__calculate-sum-products-cost, .basket__calculate-total-price-value");
  totalPriceElements.forEach(element => {
    element.textContent = `${final_price} грн.`;
  });
  
  // Додаємо інформацію про знижку
  const calculateBlock = document.querySelector(".basket__calculate");
  if (calculateBlock) {
    // Перевіряємо чи вже є блок зі знижкою
    let discountBlock = calculateBlock.querySelector(".basket__calculate-discount");
    
    if (!discountBlock) {
      discountBlock = document.createElement("div");
      discountBlock.className = "basket__calculate-discount basket_right_block";
      discountBlock.innerHTML = `
        <p class="basket__calculate-discount-title">Знижка</p>
        <p class="basket__calculate-discount-value color_gold">-${discount_percent}%</p>
      `;
      
      // Вставляємо блок зі знижкою після блоку з ціною товарів
      const sumProductsBlock = calculateBlock.querySelector(".basket__calculate-sum-products");
      sumProductsBlock.after(discountBlock);
    } else {
      discountBlock.querySelector(".basket__calculate-discount-value").textContent = `-${discount_percent}%`;
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