import "./index.scss";
import "./checkout";
import { removeFromBasket } from "../../../api/basket";
import { delete_item } from "../../module/shop_scripts/basket_action";

document.addEventListener("click", ({ target }) => {
  const deleteButton = target.closest(".basket_item__delete button");

  if (deleteButton) {
    const product = deleteButton.closest(".basket_item");
    const productId = Number(product.dataset.itemId);

    removeFromBasket(productId, () =>
      delete_item(deleteButton, ".basket_item")
    );
  }
});
