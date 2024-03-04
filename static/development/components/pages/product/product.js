import { addToBasket } from "../../../api/basket";
import { addToFavorite, removeFromFavorite } from "../../../api/favorites";

document.addEventListener("click", async ({ target }) => {
  const addToBasketButton = target.closest(".add-to-cart");
  const addToFavoriteButton = target.closest(".product_favourite-btn");

  // add to basket
  if (addToBasketButton) {
    const product = addToBasketButton.closest(".product");
    const productId = product?.dataset?.productId;

    const basketProduct = await addToBasket({
      product: productId,
      quantity: 1,
    });

    console.log(basketProduct);
  }

  // add to favourite
  if (addToFavoriteButton) {
    const product = addToFavoriteButton.closest(".product");
    const productId = product?.dataset?.productId;

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
});
