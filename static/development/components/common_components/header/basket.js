import { addToBasket } from "../../../api/basket";
import { syncStockUI } from "../../module/stock_availability";

document.addEventListener("click", async ({ target }) => {
  const addToBasketButton = target.closest(".cart_item__add-to-cart-btn");

  if (!addToBasketButton) return;

  const product = addToBasketButton.closest(".cart_item");
  if (!product) return;

  const active = product.querySelector(".sizes-block .size-label.active");
  const inStock = !active || active.dataset.inStock === "1";
  const action = addToBasketButton.dataset.action || (inStock ? "cart" : "inquire");

  if (action === "inquire" || !inStock) {
    // відкриє stock_availability listener через синтетичний клік на ask
    // або напряму — диспатчимо custom event
    product.dispatchEvent(
      new CustomEvent("open-stock-inquiry", { bubbles: true })
    );
    return;
  }

  const productId = product?.dataset?.productId;

  await addToBasket({
    product: productId,
    quantity: 1,
  });
});

// після динамічних оновлень
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".cart_item").forEach(syncStockUI);
});
