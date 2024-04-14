import { getProductsBySearchQuery } from "../../../api/search";

const searchInput = document.querySelector(".header__search input");
const searchBody = document.querySelector(".header__search-body");
const searchBodyResults = searchBody.querySelector(".header__search-items");

const renderSearchItem = ({
  id,
  title,
  image,
  product_attributes,
  href,
}) => `                
<div class="header__search-product">
<div class="header__search-product-left">
  <div class="header__search-product-img">
    <a href="#">
      <img src="${image}" />
    </a>
  </div>
  <div class="header__search-product-info">
    <a href="#">
      <h4 class="header__search-product-title truncate">
       ${title}
      </h4>
    </a>
  </div>
</div>
<div class="header__search-product-right">
  <p class="header__search-product-price">
    <span class="header__search-product-price-current">
      10000 грн
    </span>
    <span class="header__search-product-price-discount">
      43%
    </span>
    <span class="header__search-product-price-old">
      100000 грн
    </span>
  </p>
</div>
</div>`;

const renderSearchResults = (searchResults) => {
  const renderedSearchResults = searchResults?.map((item) =>
    renderSearchItem(item)
  );

  if (renderedSearchResults?.length) {
    searchBodyResults.innerHTML = renderedSearchResults.join("");
  } else {
    searchBodyResults.innerHTML =
      "<p class='header__search-text'>Товарів не знайдено 🥲</p>";
  }
};

const onSearch = async () => {
  let findedProducts = [];

  if (searchInput.value.length) {
    findedProducts = await getProductsBySearchQuery(searchInput.value);
  }

  renderSearchResults(findedProducts);
};

if (searchInput) {
  searchInput.addEventListener("input", async () => {
    searchBody.classList.add("active");

    onSearch();
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
