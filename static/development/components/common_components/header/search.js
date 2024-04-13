import { getProductsBySearchQuery } from "../../../api/search";

const searchInput = document.querySelector(".header__search input");
const searchBody = document.querySelector(".header__search-body");

if (searchInput) {
  searchInput.addEventListener("input", async () => {
    searchBody.classList.add("active");

    if (searchInput.value.length) {
      const findedProducts = await getProductsBySearchQuery(searchInput.value);

      console.log(findedProducts);
    }
  });
}

if (searchBody) {
  document.addEventListener("click", ({ target }) => {
    if (target.closest(".header__search-head")) {
      searchBody.classList.toggle("active");
    }
    if (!target.closest(".header")) {
      searchBody.classList.remove("active");
    }
  });
}
