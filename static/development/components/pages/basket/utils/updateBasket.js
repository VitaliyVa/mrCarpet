const formatCartCountLabel = (count) => {
  const abs = Math.abs(count) % 100;
  const last = abs % 10;

  if (abs > 10 && abs < 20) return `${count} товарів`;
  if (last === 1) return `${count} товар`;
  if (last >= 2 && last <= 4) return `${count} товари`;
  return `${count} товарів`;
};

export const updateBasket = (basket) => {
  const basketElement = document.querySelector(".basket");

  if (!basketElement || !basket) {
    return;
  }

  const totalPriceForProducts = basketElement.querySelector(
    ".basket__calculate-sum-products-cost"
  );
  const totalPrice = basketElement.querySelector(
    ".basket__calculate-total-price-value"
  );

  if (totalPriceForProducts) {
    totalPriceForProducts.textContent = basket.total_price;
  }
  if (totalPrice) {
    totalPrice.textContent = basket.total_price;
  }

  const itemsCount = basket.cart_products?.length ?? 0;
  const isEmpty = itemsCount === 0;
  const emptyCartBlock = document.getElementById("empty-cart-block");
  const basketCenter =
    document.getElementById("checkout-content") ||
    basketElement.querySelector(".basket__center");
  const cartCount =
    document.getElementById("cart-count") ||
    basketElement.querySelector(".title > span");

  if (cartCount) {
    cartCount.textContent = formatCartCountLabel(itemsCount);
  }

  if (typeof window !== "undefined") {
    window.cartProductsCount = itemsCount;
  }

  if (isEmpty) {
    if (emptyCartBlock) {
      emptyCartBlock.style.display = "flex";
    }
    if (basketCenter) {
      basketCenter.style.display = "none";
    }
    return;
  }

  if (emptyCartBlock) {
    emptyCartBlock.style.display = "none";
  }
  if (basketCenter) {
    basketCenter.style.display = "";
  }
};
