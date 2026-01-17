import { addToFavorite, removeFromFavorite } from "../../../api/favorites";

document.addEventListener("click", async ({ target }) => {
  const addToFavoriteButton = target.closest(".cart_item_add_to_favorite");

  if (addToFavoriteButton) {
    const product = addToFavoriteButton.closest(".cart_item");
    const productId = product?.dataset?.productId;

    const isAdded = addToFavoriteButton.classList.contains("active");

    if (!isAdded) {
      await addToFavorite(productId, () => {
        // Використовуємо requestAnimationFrame для гарантії що DOM оновився
        requestAnimationFrame(() => {
          addToFavoriteButton.classList.add("active");
        });
      });
    } else {
      await removeFromFavorite(productId, () => {
        // Використовуємо requestAnimationFrame для гарантії що DOM оновився
        requestAnimationFrame(() => {
          addToFavoriteButton.classList.remove("active");
        });
      });
    }
  }
});
