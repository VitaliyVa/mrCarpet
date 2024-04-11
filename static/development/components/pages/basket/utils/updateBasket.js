export const updateBasket = (basket) => {
  const basketElement = document.querySelector(".basket");

  if (basketElement) {
    const totalPriceForProducts = basketElement.querySelector(
      ".basket__calculate-sum-products-cost"
    );

    const totalPrice = basketElement.querySelector(
      ".basket__calculate-total-price-value"
    );

    totalPriceForProducts.textContent = basket.total_price;
    totalPrice.textContent = basket.total_price;
  }
};
