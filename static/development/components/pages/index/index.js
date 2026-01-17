import "./index.scss";

// Таймер акцій
function initSaleTimer() {
  // Знаходимо всі таймери акцій і перевіряємо їх секції
  const timerElements = document.querySelectorAll('.info_for_product__timer[data-end-time]');
  
  if (!timerElements.length) {
    return;
  }
  
  timerElements.forEach((timerElement) => {
    // Знаходимо батьківську секцію акцій
    const section = timerElement.closest('.catalog_slider');
    if (!section) {
      return;
    }
    
    const sliderWrapper = section.querySelector('.slider__block.swiper-wrapper');
    const saleProducts = sliderWrapper ? sliderWrapper.querySelectorAll('.swiper-slide') : [];
    
    // Перевіряємо чи є товари в акції
    if (!saleProducts || saleProducts.length === 0) {
      section.style.display = 'none';
      return;
    }
    
    const endTimeStr = timerElement.getAttribute('data-end-time');
    
    // Якщо немає data-end-time або він порожній - приховуємо всю секцію
    if (!endTimeStr || !endTimeStr.trim()) {
      section.style.display = 'none';
      return;
    }
    
    const endTime = new Date(endTimeStr).getTime();
    
    // Перевірка чи дата валідна
    if (isNaN(endTime)) {
      section.style.display = 'none';
      return;
    }
    
    // Функція для оновлення таймера
    function updateTimer() {
      const now = new Date().getTime();
      const distance = endTime - now;
      
      // Якщо час вийшов
      if (distance < 0) {
        timerElement.textContent = '00:00:00';
        return;
      }
      
      // Обчислюємо години, хвилини, секунди
      const hours = Math.floor((distance % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
      const minutes = Math.floor((distance % (1000 * 60 * 60)) / (1000 * 60));
      const seconds = Math.floor((distance % (1000 * 60)) / 1000);
      
      // Форматуємо з двома цифрами
      const formattedHours = String(hours).padStart(2, '0');
      const formattedMinutes = String(minutes).padStart(2, '0');
      const formattedSeconds = String(seconds).padStart(2, '0');
      
      // Оновлюємо текст
      timerElement.textContent = `${formattedHours}:${formattedMinutes}:${formattedSeconds}`;
    }
    
    // Оновлюємо таймер одразу
    updateTimer();
    
    // Оновлюємо таймер кожну секунду
    setInterval(updateTimer, 1000);
  });
}

// Ініціалізація таймера при завантаженні сторінки
document.addEventListener('DOMContentLoaded', initSaleTimer);
