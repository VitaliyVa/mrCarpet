// Обробка пагінації
document.addEventListener("click", ({ target }) => {
  const paginationLink = target.closest(".pagination a");
  
  if (paginationLink && !paginationLink.classList.contains("active")) {
    // Отримуємо поточні параметри URL
    const currentUrl = new URL(window.location);
    const pageParam = paginationLink.getAttribute("href");
    
    if (pageParam && pageParam !== "#") {
      // Оновлюємо параметр page в URL
      const newUrl = new URL(pageParam, window.location.origin);
      
      // Зберігаємо всі інші параметри (фільтри, сортування тощо)
      currentUrl.searchParams.forEach((value, key) => {
        if (key !== "page") {
          newUrl.searchParams.set(key, value);
        }
      });
      
      // Переходимо на нову сторінку
      window.location.href = newUrl.toString();
    }
  }
});

// Функція для оновлення пагінації через AJAX (опціонально)
function updatePagination(page) {
  const currentUrl = new URL(window.location);
  currentUrl.searchParams.set("page", page);
  
  fetch(currentUrl.toString())
    .then(response => response.text())
    .then(html => {
      // Оновлюємо тільки контент каталогу
      const parser = new DOMParser();
      const doc = parser.parseFromString(html, "text/html");
      
      const newProducts = doc.querySelector(".catalog_section_bottom");
      const newPagination = doc.querySelector(".pagination");
      
      if (newProducts) {
        document.querySelector(".catalog_section_bottom").innerHTML = newProducts.innerHTML;
      }
      
      if (newPagination) {
        document.querySelector(".pagination").innerHTML = newPagination.innerHTML;
      }
      
      // Оновлюємо URL без перезавантаження сторінки
      window.history.pushState({}, "", currentUrl.toString());
    })
    .catch(error => {
      console.error("Помилка при оновленні пагінації:", error);
    });
} 