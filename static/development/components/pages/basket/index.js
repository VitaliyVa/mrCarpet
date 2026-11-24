import "./index.scss";
import "./checkout";
import { removeFromBasket, updateBasketItem } from "../../../api/basket";
import {
  delete_item,
  minus,
  plus,
} from "../../module/shop_scripts/basket_action";
import { initPromocode, restorePromocode } from "./promocode";
import {
  itemFromProductEl,
  itemsValue,
  parseMoney,
  trackEcommerce,
} from "../../../utils/analytics";

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
        trackQuantityChange(basketProduct);
      }
    };

    // Quantity +/- in the cart is add_to_cart / remove_from_cart for the
    // difference, priced per unit from the server line total.
    const trackQuantityChange = (basketProduct) => {
      const before = Number(product.dataset.quantity) || 1;
      const after = Number(basketProduct.quantity) || before;
      const lineTotal = parseMoney(basketProduct.total_price);
      product.dataset.quantity = String(after);
      product.dataset.price = String(lineTotal);
      const diff = after - before;
      if (!diff) return;
      const unit = after ? lineTotal / after : 0;
      const item = itemFromProductEl(product, {
        quantity: Math.abs(diff),
        price: unit,
        item_variant: product.dataset.itemVariant || "",
      });
      if (!item?.item_id) return;
      trackEcommerce(diff > 0 ? "add_to_cart" : "remove_from_cart", {
        value: itemsValue([item]),
        items: [item],
      });
    };

    if (deleteButton) {
      const qty = Number(product.dataset.quantity) || 1;
      const lineTotal = parseMoney(product.dataset.price);
      const analyticsItem = itemFromProductEl(product, {
        quantity: qty,
        price: qty ? lineTotal / qty : lineTotal,
        item_variant: product.dataset.itemVariant || "",
      });
      removeFromBasket(
        productId,
        () => delete_item(deleteButton, ".basket_item"),
        analyticsItem
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
