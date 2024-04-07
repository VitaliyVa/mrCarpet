import { addToBasket } from "../../../api/basket";
import { addToFavorite, removeFromFavorite } from "../../../api/favorites";
import { minus, plus } from "../../module/shop_scripts/basket_action";

document.addEventListener("click", async ({ target }) => {
  const product = target.closest(".product");
  const productId = product?.dataset?.productId;

  const addToBasketButton = target.closest(".add-to-cart");
  const addToFavoriteButton = target.closest(".product_favourite-btn");

  const counterMinusButton = target.closest(".counter__minus-btn");
  const counterPlusButton = target.closest(".counter__plus-btn");

  // add to basket
  if (addToBasketButton) {
    const counterValue = product.querySelector(".counter__value").value;

    const basketProduct = await addToBasket({
      product: productId,
      quantity: Number(counterValue) || 1,
    });

    console.log(basketProduct);
  }

  // add to favourite
  if (addToFavoriteButton) {
    const isAdded = addToFavoriteButton.classList.contains("active");

    if (!isAdded) {
      await addToFavorite(productId, () =>
        addToFavoriteButton.classList.add("active")
      );
    } else {
      await removeFromFavorite(productId, () =>
        addToFavoriteButton.classList.remove("active")
      );
    }
  }

  if (counterMinusButton) {
    minus(".counter", ".counter__value", target);
  }

  if (counterPlusButton) {
    plus(".counter", ".counter__value", target);
  }
});
