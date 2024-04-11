import "./index.scss";

document.addEventListener("click", ({ target }) => {
  const sizeLabel = target.closest(".size-label");

  if (sizeLabel) {
    const product =
      sizeLabel.closest(".cart_item") || sizeLabel.closest(".product");

    if (product) {
      const newLabelProduct = product.querySelector(".cart_item_new ");
      const sizesBlock = product.querySelector(".sizes-block");
      const allSizeLabels = sizesBlock.querySelectorAll(".size-label");
      const { item, novelty } = sizeLabel.dataset;

      const priceProduct = product.querySelector(".cart_item_price");
      const discountProduct = product.querySelector(".cart_item_procent");
      const oldPriceProduct = product.querySelector(".cart_item_old_price");

      const priceProductValue = product.querySelector(".cart_item_price-value");
      const oldPriceProductValue = product.querySelector(
        ".cart_item_old_price-value"
      );

      const newPriceProduct = priceProduct.dataset[`item-${item}`];
      const newDiscountProduct = discountProduct.dataset[`item-${item}`];
      const newOldPriceProduct = oldPriceProduct.dataset[`item-${item}`];

      allSizeLabels.forEach((item) => {
        item.classList.remove("active");
      });

      sizeLabel.classList.add("active");

      product.dataset.productId = item;
      priceProductValue.textContent = newPriceProduct;
      discountProduct.textContent = newDiscountProduct;
      oldPriceProductValue.textContent = newOldPriceProduct;

      if (newLabelProduct) {
        if (novelty === "false") {
          newLabelProduct.classList.add("disabled");
        } else {
          newLabelProduct.classList.remove("disabled");
        }
      }
    }
  }
});
