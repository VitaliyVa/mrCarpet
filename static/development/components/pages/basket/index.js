import "./index.scss";
import "./checkout";
import { removeFromBasket, updateBasketItem } from "../../../api/basket";
import {
  delete_item,
  minus,
  plus,
} from "../../module/shop_scripts/basket_action";

document.addEventListener("click", ({ target }) => {
  const product = target.closest(".basket_item");

  if (product) {
    const productId = Number(product.dataset.itemId);

    const deleteButton = target.closest(".basket_item__delete button");

    const counterMinusButton = target.closest(".counter__minus-btn");
    const counterPlusButton = target.closest(".counter__plus-btn");
    const counterValue =
      Number(product.querySelector(".counter__value").value) || 1;

    if (deleteButton) {
      removeFromBasket(productId, () =>
        delete_item(deleteButton, ".basket_item")
      );
    }

    if (counterMinusButton) {
      updateBasketItem({ id: productId, quantity: 1 }, () =>
        minus(".counter", ".counter__value", target)
      );
    }

    if (counterPlusButton) {
      updateBasketItem({ id: productId, quantity: 1 }, () =>
        plus(".counter", ".counter__value", target)
      );
    }
  }
});
