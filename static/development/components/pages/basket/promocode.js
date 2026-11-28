import "./promocode.scss";
import { instance } from "../../../api/instance";
import { showSuccess, showError } from "./notification";
import { trackEvent } from "../../../utils/analytics";
import { goToNewsletterSubscribe } from "../../common_components/footer/subscription";
import { updateFreeShippingUI } from "./utils/freeShipping";

function positionPromoTip(anchor, tooltip) {
  tooltip.style.display = "block";
  tooltip.style.visibility = "hidden";
  tooltip.style.left = "-9999px";
  tooltip.style.top = "0";

  const tooltipHeight = tooltip.offsetHeight;
  const tooltipWidth = tooltip.offsetWidth;
  const rect = anchor.getBoundingClientRect();
  const gap = 8;
  const margin = 12;

  let top = rect.top - tooltipHeight - gap;
  let left = rect.left;
  let below = false;

  if (top < margin) {
    top = rect.bottom + gap;
    below = true;
  }

  if (left + tooltipWidth > window.innerWidth - margin) {
    left = window.innerWidth - tooltipWidth - margin;
  }

  if (left < margin) {
    left = margin;
  }

  tooltip.classList.toggle("is-below", below);
  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;
  tooltip.style.visibility = "";
}

function openPromoTip(tip) {
  const tooltip = tip.querySelector(".basket__promo-tip-tooltip");
  const mark = tip.querySelector(".basket__promo-tip-mark");
  if (!tooltip || !mark) return;

  if (tooltip.parentElement !== document.body) {
    document.body.appendChild(tooltip);
  }

  positionPromoTip(mark, tooltip);
  tooltip.classList.add("is-visible");
  tip.classList.add("is-open");
}

function closePromoTip(tip) {
  const tipId = tip.dataset.tipId;
  const tooltip =
    document.querySelector(`.basket__promo-tip-tooltip[data-tip-for="${tipId}"]`) ||
    tip.querySelector(".basket__promo-tip-tooltip");

  tip.classList.remove("is-open");
  if (!tooltip) return;

  tooltip.classList.remove("is-visible");
  tip.appendChild(tooltip);
}

function initPromoTip() {
  const tips = document.querySelectorAll(".basket__promo-tip");
  if (!tips.length) return;

  const hasHover = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
  const hideTimers = new WeakMap();

  tips.forEach((tip, index) => {
    const tooltip = tip.querySelector(".basket__promo-tip-tooltip");
    const tipId = `promo-tip-${index}`;
    tip.dataset.tipId = tipId;

    if (tooltip) {
      tooltip.dataset.tipFor = tipId;
    }

    const scheduleClose = () => {
      clearTimeout(hideTimers.get(tip));
      hideTimers.set(tip, setTimeout(() => closePromoTip(tip), 160));
    };

    const cancelClose = () => {
      clearTimeout(hideTimers.get(tip));
    };

    if (hasHover) {
      tip.addEventListener("mouseenter", () => {
        cancelClose();
        openPromoTip(tip);
      });
      tip.addEventListener("mouseleave", scheduleClose);

      if (tooltip) {
        tooltip.addEventListener("mouseenter", cancelClose);
        tooltip.addEventListener("mouseleave", scheduleClose);
      }
    }

    tip.addEventListener("focus", () => openPromoTip(tip));
    tip.addEventListener("blur", () => closePromoTip(tip));

    tip.addEventListener("click", (event) => {
      if (event.target.closest(".basket__promo-tip-link")) return;
      if (hasHover) return;

      event.preventDefault();
      event.stopPropagation();
      const isOpen = tip.classList.contains("is-open");
      tips.forEach((item) => closePromoTip(item));
      if (!isOpen) openPromoTip(tip);
    });
  });

  window.addEventListener("resize", () => {
    tips.forEach((tip) => {
      if (!tip.classList.contains("is-open")) return;
      const tooltip = document.querySelector(
        `.basket__promo-tip-tooltip[data-tip-for="${tip.dataset.tipId}"]`
      );
      const mark = tip.querySelector(".basket__promo-tip-mark");
      if (tooltip && mark) positionPromoTip(mark, tooltip);
    });
  });

  document.addEventListener("click", (event) => {
    if (event.target.closest(".basket__promo-tip")) return;
    if (event.target.closest(".basket__promo-tip-tooltip")) return;
    tips.forEach((tip) => closePromoTip(tip));
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      tips.forEach((tip) => closePromoTip(tip));
    }
  });

  document.addEventListener("click", (event) => {
    const link = event.target.closest(".basket__promo-tip-link");
    if (!link) return;

    tips.forEach((tip) => closePromoTip(tip));
    event.preventDefault();
    goToNewsletterSubscribe();
  });
}

// Функціональність для промокоду
let promocodeBound = false;

export function initPromocode() {
  // Both basket/index.js and basket/checkout.js call this from one bundle:
  // two click listeners sent every code twice (two requests, two toasts).
  if (promocodeBound) return;
  promocodeBound = true;
  console.log("initPromocode called"); // Логування
  initPromoTip();

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
      
      const emailInput = document.querySelector(
        '#checkout-form input[name="email"], input[name="email"]'
      );
      const email = emailInput?.value?.trim() || "";

      // Відправляємо запит на перевірку промокоду
      instance.post("/check-promocode/", { promocode, email })
        .then(({ data }) => {
          console.log("Response received:", data); // Логування
          
          if (data.success) {
            // Оновлюємо ціни на сторінці
            updatePricesWithDiscount(data);
            
            // Показуємо повідомлення про успіх
            showSuccess(data.message || "Промокод успішно застосовано!");
            
            // Зберігаємо промокод в localStorage для подальшого використання
            localStorage.setItem('applied_promocode', promocode);
            
            trackEvent("promo_applied", {
              coupon: promocode.toUpperCase().slice(0, 40),
              discount: Number(data.discount_amount) || 0,
              discount_percent: Number(data.discount_percent) || 0,
              page_type: window.__mrPageType || "",
            });

            // Змінюємо вигляд кнопки
            promocodeButton.textContent = "Застосовано";
            promocodeButton.classList.add("applied");
          }
        })
        .catch(({ response }) => {
          console.log("Error occurred:", response); // Логування
          
          // Показуємо повідомлення про помилку
          const errorMessage = response?.data?.error || "Помилка при перевірці промокоду";
          // Not the typed text: a wrong "code" is often a phone or a name.
          trackEvent("promo_failed", {
            reason: String(errorMessage).slice(0, 100),
            http_status: response?.status || 0,
          });
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