// Система сповіщень для checkout
let notificationTimeout = null;

// Показати notification
function showNotification(message, type = "success") {
  // Видаляємо попереднє notification якщо є
  const existingNotification = document.querySelector(".checkout-notification");
  if (existingNotification) {
    existingNotification.remove();
  }

  // Очищаємо попередній таймер
  if (notificationTimeout) {
    clearTimeout(notificationTimeout);
  }

  // Створюємо notification
  const notification = document.createElement("div");
  notification.className = `checkout-notification checkout-notification--${type}`;
  
  // Іконка в залежності від типу
  const icon = type === "success" 
    ? '<svg width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M10 0C4.48 0 0 4.48 0 10C0 15.52 4.48 20 10 20C15.52 20 20 15.52 20 10C20 4.48 15.52 0 10 0ZM8 15L3 10L4.41 8.59L8 12.17L15.59 4.58L17 6L8 15Z" fill="currentColor"/></svg>'
    : '<svg width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M10 0C4.48 0 0 4.48 0 10C0 15.52 4.48 20 10 20C15.52 20 20 15.52 20 10C20 4.48 15.52 0 10 0ZM11 15H9V13H11V15ZM11 11H9V5H11V11Z" fill="currentColor"/></svg>';
  
  notification.innerHTML = `
    <div class="checkout-notification__icon">${icon}</div>
    <div class="checkout-notification__message">${message}</div>
    <button class="checkout-notification__close" aria-label="Закрити">
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
        <path d="M14 1.41L12.59 0L7 5.59L1.41 0L0 1.41L5.59 7L0 12.59L1.41 14L7 8.41L12.59 14L14 12.59L8.41 7L14 1.41Z" fill="currentColor"/>
      </svg>
    </button>
  `;

  // Додаємо в body
  document.body.appendChild(notification);

  // Анімація появи
  setTimeout(() => {
    notification.classList.add("checkout-notification--show");
  }, 10);

  // Обробник закриття
  const closeBtn = notification.querySelector(".checkout-notification__close");
  closeBtn.addEventListener("click", () => {
    hideNotification(notification);
  });

  // Автоматично ховаємо через 5 секунд
  notificationTimeout = setTimeout(() => {
    hideNotification(notification);
  }, 5000);
}

// Сховати notification
function hideNotification(notification) {
  notification.classList.remove("checkout-notification--show");
  setTimeout(() => {
    notification.remove();
  }, 300);
}

// Експортуємо функції
export function showSuccess(message) {
  showNotification(message, "success");
}

export function showError(message) {
  showNotification(message, "error");
}

export function showInfo(message) {
  showNotification(message, "info");
}

