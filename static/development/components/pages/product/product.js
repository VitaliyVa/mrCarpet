import { addToFavorite, removeFromFavorite } from "../../../api/favorites";

document.addEventListener("click", async ({ target }) => {
  const addToFavoriteButton = target.closest(".product_favourite-btn");

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
