const searchInput = document.querySelector(".header__search input");
const searchBody = document.querySelector(".header__search-body");

if (searchInput) {
  searchInput.addEventListener("input", () => {
    searchBody.classList.add("active");
  });
}

document.addEventListener("click", ({ target }) => {
  if (target.closest(".header__search-head")) {
    searchBody.classList.toggle("active");
  }
  if (!target.closest(".header")) {
    searchBody.classList.remove("active");
  }
});
