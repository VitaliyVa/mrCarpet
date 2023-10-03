import "./index.scss";

const starRateAllItems = document.querySelectorAll(".star-rate");

starRateAllItems.forEach((starRate) => {
  const starRateItems = starRate.querySelectorAll(".star-rate__item");

  starRateItems.forEach((item) => {
    const itemInputValue = Number(item.querySelector("input").value);

    if (itemInputValue <= starRate.dataset.ratingValue) {
      item.classList.add("active");
    }
  });
});

document.addEventListener("click", ({ target }) => {
  const starRate = target.closest(".star-rate");
  const starRateItems = starRate.querySelectorAll(".star-rate__item");
  const currentStarItem = target.closest(".star-rate__item");

  if (currentStarItem) {
    const currentStarItemInputValue = Number(
      currentStarItem.querySelector("input").value
    );

    starRateItems.forEach((item) => {
      const itemInputValue = Number(item.querySelector("input").value);

      if (itemInputValue <= currentStarItemInputValue) {
        item.classList.add("active");
        starRate.dataset.ratingValue = currentStarItemInputValue;
      } else {
        item.classList.remove("active");
      }
    });
  }
});
