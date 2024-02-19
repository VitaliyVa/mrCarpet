import { addToFavorite } from "../../../api/favorites";

document.addEventListener("click", async ({ target }) => {
  const addToFavoriteButton = target.closest(".cart_item_add_to_favorite");

  if (addToFavoriteButton) {
    const product = addToFavoriteButton.closest(".cart_item");
    const productId = product?.dataset?.productId;

    const favoriteProduct = await addToFavorite(productId);

    console.log(favoriteProduct);
  }
});
