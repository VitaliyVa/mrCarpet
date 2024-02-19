import { addToBasket } from "../../../api/basket";

document.addEventListener("click", async ({ target }) => {
  //   змінити на актуаьну назву для кнопки додавання в корзину
  const addToBasketButton = target.closest(".product__btn");

  if (addToBasketButton) {
    const product = addToBasketButton.closest(".product__btn");
    const productId = product?.dataset?.productId;

    const basketProduct = await addToBasket({
      product: productId,
      quantity: 1,
    });

    console.log(basketProduct);
  }
});
