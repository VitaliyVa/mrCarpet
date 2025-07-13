import "./index.scss";
import "./checkout";
import { removeFromBasket, updateBasketItem } from "../../../api/basket";
import {
  delete_item,
  minus,
  plus,
} from "../../module/shop_scripts/basket_action";
import { initPromocode, restorePromocode } from "./promocode";

console.log("Basket index.js loaded"); // Логування

document.addEventListener("click", ({ target }) => {
  const product = target.closest(".basket_item");

  if (product) {
    const productId = Number(product.dataset.itemId);

    const deleteButton = target.closest(".basket_item__delete button");

    const counterMinusButton = target.closest(".counter__minus-btn");
    const counterPlusButton = target.closest(".counter__plus-btn");

    const updateCardItem = (basket) => {
      const productTotalPrice = product.querySelector(".cart_item_total-price");

      const basketProduct = basket?.cart_products.find(
        (basketItem) => basketItem.id === productId
      );

      if (basketProduct) {
        // Використовуємо total_price з серіалізатора, який вже містить правильну ціну
        productTotalPrice.textContent = basketProduct.total_price;
      }
    };

    if (deleteButton) {
      removeFromBasket(productId, () =>
        delete_item(deleteButton, ".basket_item")
      );
    }

    if (counterMinusButton) {
      updateBasketItem(
        { id: productId, quantity: 1, increment: false },
        (basket) => {
          minus(".counter", ".counter__value", target);
          updateCardItem(basket);
        }
      );
    }

    if (counterPlusButton) {
      updateBasketItem(
        { id: productId, quantity: 1, increment: true },
        (basket) => {
          plus(".counter", ".counter__value", target);
          updateCardItem(basket);
        }
      );
    }
  }
});

// Ініціалізуємо функціональність промокоду
console.log("Calling initPromocode..."); // Логування
initPromocode();
console.log("initPromocode called successfully"); // Логування

// Відновлюємо застосований промокод при завантаженні сторінки
document.addEventListener("DOMContentLoaded", () => {
  console.log("DOMContentLoaded event fired"); // Логування
  restorePromocode();
});
