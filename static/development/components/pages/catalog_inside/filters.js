const filters = document.querySelector(".catalog_inside_filter");

document.addEventListener("click", ({ target }) => {
  if (target.closest(".catalog_inside_filter-btn")) {
    filters.classList.add("active");
  }

  if (target.closest(".catalog_inside_filter-close-btn")) {
    filters.classList.remove("active");
  }
});
