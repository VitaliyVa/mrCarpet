import { addToBasket } from "../../../api/basket";

document.addEventListener("click", async ({ target }) => {
  const addToBasketButton = target.closest(".cart_item__add-to-cart-btn");

  if (addToBasketButton) {
    const product = addToBasketButton.closest(".cart_item");
    const productId = product?.dataset?.productId;

    const basketProduct = await addToBasket({
      product: productId,
      quantity: 1,
    });

    console.log(basketProduct);
  }
});
