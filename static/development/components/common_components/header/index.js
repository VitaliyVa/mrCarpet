import "./authorization";
import "./search";
import "./contacts";

import "./index.scss";
import "./authorization.scss";
import "./contacts-modal.scss";

const headerMain = document.querySelector(".header");
const header = document.querySelector(".header_bottom_panel__block");
const catalog_bg = document.querySelectorAll(".header_bottom_panel_catalog_bg");
const catalog_content = document.querySelectorAll(".header_content__block");
const panel = document.querySelector(".header_bottom_panel_catalog");
const search = document.querySelector(".header_bottom_panel_search");

function toggleActiveCatalog() {
  panel.toggle = function () {
    panel.classList.toggle("active");
    headerMain.classList.toggle("active");
    catalog_bg.forEach((element) => {
      element.classList.toggle("active");
    });
    catalog_content.forEach((element) => {
      element.classList.toggle("active");
    });
    if (
      header.classList.contains("fixed") &&
      panel.classList.contains("active")
    ) {
      catalog_bg.forEach((element) => {
        element.classList.add("fixed");
      });
      catalog_content.forEach((element) => {
        element.classList.add("fixed");
      });
    } else {
      catalog_bg.forEach((element) => {
        element.classList.remove("fixed");
      });
      catalog_content.forEach((element) => {
        element.classList.remove("fixed");
      });
    }
  };

  panel.addEventListener("click", panel.toggle);
}

toggleActiveCatalog();

function headerPanelScroll() {
  // Получаем элемент header и позицию его верхней границы

  const headerTop = header.offsetTop;

  // Функция, которая будет вызываться при скролле
  function handleScroll() {
    // Получаем текущую позицию скролла
    const scrollY = window.scrollY;

    // Если скролл больше или равен позиции верхней границы header
    if (scrollY >= headerTop) {
      // Добавляем класс 'fixed' к header
      header.classList.add("fixed");

      if (panel.classList.contains("active")) {
        catalog_bg.forEach((element) => {
          element.classList.add("fixed");
        });
        catalog_content.forEach((element) => {
          element.classList.add("fixed");
        });
      }
    } else {
      // Удаляем класс 'fixed' из header
      header.classList.remove("fixed");
      if (panel.classList.contains("active")) {
        catalog_bg.forEach((element) => {
          element.classList.remove("fixed");
        });
        catalog_content.forEach((element) => {
          element.classList.remove("fixed");
        });
      }
    }
  }

  // Добавляем обработчик события 'scroll' к window
  window.addEventListener("scroll", handleScroll);
}
headerPanelScroll();

function toggleActiveSearch() {
  document.addEventListener("click", function (event) {
    if (event.target !== search && !search.contains(event.target)) {
      search.classList.remove("active");
    }
  });

  search.addEventListener("click", (e) => {
    search.classList.add("active");
  });
}
toggleActiveSearch();
