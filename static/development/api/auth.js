import { instance } from "./instance";
import { showLoader, hideLoader } from "../components/module/form_action";
import { showSuccess, showError } from "../utils/notifications";

export const loginUser = async (values) => {
  showLoader();

  try {
    const { data } = await instance.post("/users/user_login/", values);

    hideLoader();
    
    // Закриваємо модальне вікно одразу без повідомлення про успіх
    const loginModal = document.querySelector('.login-modal');
    const modalOverlay = loginModal?.closest('.modal-overlay');
    
    if (loginModal && modalOverlay) {
      // Видаляємо клас active з модального вікна та overlay
      loginModal.classList.remove('active');
      modalOverlay.classList.remove('active');
      // Повертаємо прокрутку body
      document.body.style.overflowY = 'initial';
    }
    
    // Перезавантажуємо сторінку одразу без затримок
    window.location.reload();

    return data;
  } catch (error) {
    hideLoader();
    
    // Обробка помилок від axios
    if (error.response) {
      // Сервер повернув помилку (4xx, 5xx)
      const responseData = error.response.data;
      
      // Отримуємо повідомлення про помилку
      let errorMessage = "Помилка авторизації";
      
      if (responseData) {
        if (typeof responseData === 'string') {
          errorMessage = responseData;
        } else if (responseData.message) {
          errorMessage = responseData.message;
        } else if (responseData.detail) {
          errorMessage = responseData.detail;
        } else if (responseData.error) {
          errorMessage = responseData.error;
        } else if (Array.isArray(responseData) && responseData.length > 0) {
          errorMessage = responseData[0];
        }
      }
      
      // Перекладаємо повідомлення на українську
      let ukrainianMessage = errorMessage;
      if (errorMessage === "User with these credentials doesn't exist") {
        ukrainianMessage = "Користувача з такими даними не існує";
      } else if (errorMessage.includes("User with these credentials")) {
        ukrainianMessage = "Користувача з такими даними не існує";
      } else if (errorMessage.includes("credentials")) {
        ukrainianMessage = "Невірні дані для входу";
      }
      
      // Додаємо помилку безпосередньо в форму логіну
      const loginForm = document.querySelector('.login-modal__form');
      if (loginForm) {
        // Видаляємо попередні помилки
        const existingError = loginForm.querySelector('.login-form-error');
        if (existingError) {
          existingError.remove();
        }
        
        // Створюємо блок помилки
        const errorDiv = document.createElement('div');
        errorDiv.className = 'login-form-error';
        errorDiv.style.cssText = 'color: #dc3545; padding: 12px; margin-bottom: 20px; background: #f8d7da; border: 1px solid #f5c6cb; border-radius: 4px; font-size: 14px;';
        errorDiv.textContent = ukrainianMessage;
        
        // Додаємо на початок форми
        loginForm.insertBefore(errorDiv, loginForm.firstChild);
        
        // Автоматично видаляємо через 5 секунд
        setTimeout(() => {
          if (errorDiv.parentElement) {
            errorDiv.remove();
          }
        }, 5000);
      }
    } else if (error.request) {
      // Запит був зроблений, але відповіді не отримано
      console.error("Помилка мережі:", error.request);
      showError("Не вдалося з'єднатися з сервером. Перевірте інтернет-з'єднання.");
    } else {
      // Помилка при налаштуванні запиту
      console.error("Помилка налаштування:", error.message);
      showError("Помилка при відправці запиту");
    }
  }
};

export const registerUser = async (values) => {
  showLoader();

  try {
    const { data } = await instance.post("/users/register/", values);

    hideLoader();
    showSuccess("Успішно!");
    setTimeout(() => window.location.reload(), 1500);

    return data;
  } catch ({ response }) {
    hideLoader();
    showError(response?.data?.message || "Помилка реєстрації");
  }
};
