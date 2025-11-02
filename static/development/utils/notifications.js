// Глобальна система сповіщень
// Експортуємо notifications для використання по всьому проекту

import { showSuccess, showError, showInfo } from "../components/pages/basket/notification";

// Реекспортуємо для зручності
export { showSuccess, showError, showInfo };

// Alias для backward compatibility з старими модальними вікнами
export const accept_modal = (message = "Все пройшло успішно! 🎉") => {
  showSuccess(message);
};

export const bad_modal = (message = "Щось пішло не так, спробуйте пізніше!") => {
  showError(message);
};

