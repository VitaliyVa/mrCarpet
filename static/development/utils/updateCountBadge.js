export const updateCountBadge = (badgeClassName, count) => {
  const badgeElements = document.querySelectorAll(badgeClassName);

  if (badgeElements.length) {
    badgeElements.forEach((badge) => {
      const badgeCountLabel = badge.querySelector(
        ".header_bottom_panel_item_count"
      );

      if (badgeCountLabel) {
        // Видаляємо попередній клас анімації якщо він є
        badgeCountLabel.classList.remove("count-animate");
        
        // Оновлюємо текст - використовуємо 0 якщо count undefined або null
        badgeCountLabel.textContent = count !== undefined && count !== null ? count : 0;
        
        // Додаємо клас анімації для збільшення
        // Використовуємо requestAnimationFrame для гарантії що DOM оновився
        requestAnimationFrame(() => {
          badgeCountLabel.classList.add("count-animate");
          
          // Видаляємо клас після завершення анімації
          setTimeout(() => {
            badgeCountLabel.classList.remove("count-animate");
          }, 300);
        });
      }
    });
  }
};
