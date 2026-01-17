import { addToBasket } from "../../../api/basket";
import { addToFavorite, removeFromFavorite } from "../../../api/favorites";
import { minus, plus } from "../../module/shop_scripts/basket_action";

document.addEventListener("click", async ({ target }) => {
  const product = target.closest(".product");
  const productId = product?.dataset?.productId;

  const addToBasketButton = target.closest(".add-to-cart");
  const addToFavoriteButton = target.closest(".product_favourite-btn");
  const characteristicValue = target.closest(".characteristic-value");

  const counterMinusButton = target.closest(".counter__minus-btn");
  const counterPlusButton = target.closest(".counter__plus-btn");

  // click on characteristic value - redirect to catalog with filter
  if (characteristicValue) {
    const specName = characteristicValue.dataset.specName;
    const specValue = characteristicValue.dataset.specValue;
    const categorySlug = characteristicValue.dataset.categorySlug;

    if (specName && specValue && categorySlug) {
      // Перетворюємо назву специфікації в нижній регістр для URL
      const specNameLower = specName.toLowerCase();
      
      // Кодуємо значення для URL
      const encodedSpecValue = encodeURIComponent(specValue);
      
      // Будуємо URL: /catalog/categorie/{category_slug}/?{spec_name_lower}={spec_value}
      const catalogUrl = `/catalog/categorie/${categorySlug}/?${specNameLower}=${encodedSpecValue}`;
      
      // Перенаправляємо на каталог з фільтром
      window.location.href = catalogUrl;
      return;
    }
  }

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
