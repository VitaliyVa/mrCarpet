import { addToFavorite, removeFromFavorite } from "../../../api/favorites";
import { itemFromProductEl } from "../../../utils/analytics";

document.addEventListener("click", async ({ target }) => {
  const addToFavoriteButton = target.closest(".cart_item_add_to_favorite");

  if (addToFavoriteButton) {
    const product = addToFavoriteButton.closest(".cart_item");
    // API lookup = ProductAttribute.id; GA item_id = catalog Product.pk
    const productId = product?.dataset?.productId;
    const analyticsItem = itemFromProductEl(product, { quantity: 1 });

    const isAdded = addToFavoriteButton.classList.contains("active");

    if (!isAdded) {
      await addToFavorite(
        productId,
        () => {
          requestAnimationFrame(() => {
            addToFavoriteButton.classList.add("active");
          });
        },
        analyticsItem
      );
    } else {
      await removeFromFavorite(
        productId,
        () => {
          requestAnimationFrame(() => {
            addToFavoriteButton.classList.remove("active");
          });
        },
        analyticsItem
      );
    }
  }
});
