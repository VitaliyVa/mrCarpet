const filters = document.querySelector(".catalog_inside_filter");

document.addEventListener("click", ({ target }) => {
  if (target.closest(".catalog_inside_filter-btn")) {
    filters.classList.add("active");
  }

  if (target.closest(".catalog_inside_filter-close-btn")) {
    filters.classList.remove("active");
  }
});

function update_filter() {
  let params = window.location.search
    .replace("?", "")
    .split("&")
    .reduce(function (p, e) {
      if (e.length) {
        var a = e.split("=");
        p[decodeURIComponent(a[0])] = decodeURIComponent(a[1]);
        return p;
      }
    }, {});

  for (let key in params) {
    if (key !== "page") {
      const values = params[key].split(",");
      for (let value of values) {
        const input = document.querySelector(
          `[data-slug="${key}"] input[value="${value}"]`
        );

        if (input) {
          input.checked = true;
          input
            .closest(".catalog_inside_filter-body-item")
            .classList.add("active");
        }
      }
    }
  }
}

update_filter();

function filtration() {
  const filters = document.querySelectorAll(".catalog_inside_filter-body-item");
  const url_arr = [];
  let url;
  filters.forEach((filter) => {
    const select_options = filter.querySelectorAll("input:checked");

    if (select_options.length) {
      const select_options_value = [];
      select_options.forEach((option) =>
        select_options_value.push(option.value)
      );
      const param_str = `${[filter.dataset.slug]}=${[...select_options_value]}`;
      url_arr.push(param_str);
    }
  });

  url = url_arr.join("&");
  window.location = `?${url}`;
}

filters.addEventListener("click", filtration);
