import "./index.scss";
import { syncStockUI } from "../../module/stock_availability";
import { trackEvent } from "../../../utils/analytics";

document.addEventListener("click", ({ target }) => {
  const sizeLabel = target.closest(".size-label");

  if (sizeLabel) {
    const product =
      sizeLabel.closest(".cart_item") || sizeLabel.closest(".product");

    if (product) {
      const newLabelProduct = product.querySelector(".cart_item_new ");
      const sizesBlock = product.querySelector(".sizes-block");
      if (!sizesBlock) return;
      const allSizeLabels = sizesBlock.querySelectorAll(".size-label");
      const { item, novelty } = sizeLabel.dataset;

      const priceProduct = product.querySelector(".cart_item_price");
      const discountProduct = product.querySelector(".cart_item_procent");
      const oldPriceProduct = product.querySelector(".cart_item_old_price");

      const priceProductValue = product.querySelector(".cart_item_price-value");
      const oldPriceProductValue = product.querySelector(
        ".cart_item_old_price-value"
      );

      const newPriceProduct = priceProduct?.dataset[`item-${item}`];
      const newDiscountProduct = discountProduct?.dataset[`item-${item}`];
      const newOldPriceProduct = oldPriceProduct?.dataset[`item-${item}`];

      allSizeLabels.forEach((el) => {
        el.classList.remove("active");
      });

      sizeLabel.classList.add("active");

      product.dataset.productId = item;
      if (priceProductValue && newPriceProduct !== undefined) {
        priceProductValue.textContent = newPriceProduct;
      }
      if (discountProduct) {
        discountProduct.textContent = newDiscountProduct || "";
      }
      if (oldPriceProductValue) {
        oldPriceProductValue.textContent = newOldPriceProduct || "";
      }

      if (newLabelProduct) {
        if (novelty === "false") {
          newLabelProduct.classList.add("disabled");
        } else {
          newLabelProduct.classList.remove("disabled");
        }
      }

      syncStockUI(product);

      const bagBtn = product.querySelector(".cart_item__add-to-cart-btn");
      if (bagBtn) {
        const inStock = sizeLabel.dataset.inStock === "1";
        bagBtn.dataset.action = inStock ? "cart" : "inquire";
        bagBtn.title = inStock ? "Додати до кошика" : "Дізнатись про наявність";
      }

      trackEvent("size_select", {
        item_id: String(
          product.dataset.catalogProductId || product.dataset.productId || ""
        ),
        item_name: product.dataset.productTitle || "",
        size_label: sizeLabel.textContent?.trim() || String(item || ""),
        product_attr_id: String(item || ""),
      });
    }
  }
});
