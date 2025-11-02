import { initPromocode, restorePromocode } from "./promocode";
import { initNovaPost, getNovaPostData } from "./nova-post";
import { initOrderForm, checkEmptyCart } from "./order-form";

const checkboxItems = document.querySelectorAll(".basket__checkbox-item");

document.addEventListener("click", ({ target }) => {
  const accordionTitle = target.closest(".accordion__title");
  const bodyBlockEditBtn = target.closest(
    ".basket__checkbox-item-body-block-edit-btn"
  );

  // Control accordion and checkboxes
  if (accordionTitle) {
    const accordionContentBlock = accordionTitle.closest(
      ".accordion_content__block"
    );
    const checkboxInput =
      accordionContentBlock.querySelector(".checkbox__input");

    checkboxInput.checked = true;
    accordionContentBlock.classList.add("active");

    checkboxItems.forEach((item) => {
      if (!item.querySelector(".checkbox__input").checked) {
        item.classList.remove("active");
      }
    });
  }

  // Unlocking editing of address and contact data fields
  // Пропускаємо кнопки з ID для Нової Пошти (вони мають власну логіку)
  if (bodyBlockEditBtn && 
      bodyBlockEditBtn.id !== "nova-post-edit-btn" && 
      bodyBlockEditBtn.id !== "nova-post-info-edit-btn") {
    const bodyBlock = bodyBlockEditBtn.closest(
      ".basket__checkbox-item-body-block"
    );
    const bodyBlockFields = bodyBlock.querySelectorAll("input");

    if (bodyBlockEditBtn.classList.contains("active")) {
      bodyBlockEditBtn.classList.remove("active");
      bodyBlockFields.forEach((item) => (item.readOnly = true));
    } else {
      bodyBlockEditBtn.classList.add("active");
      bodyBlockFields.forEach((item) => (item.readOnly = false));
    }
  }
});

// Обробка кнопки редагування інформації для доставки (Нова Пошта)
document.addEventListener("click", ({ target }) => {
  const infoEditBtn = target.closest("#nova-post-info-edit-btn");
  
  if (infoEditBtn) {
    const bodyBlock = infoEditBtn.closest(".basket__checkbox-item-body-block");
    const bodyBlockFields = bodyBlock.querySelectorAll("input");

    if (infoEditBtn.classList.contains("active")) {
      infoEditBtn.classList.remove("active");
      bodyBlockFields.forEach((item) => (item.readOnly = true));
    } else {
      infoEditBtn.classList.add("active");
      bodyBlockFields.forEach((item) => (item.readOnly = false));
    }
  }
});

// Ініціалізуємо функціональність промокоду
initPromocode();

// Ініціалізуємо функціональність Нової Пошти
initNovaPost();

// Ініціалізуємо форму замовлення
initOrderForm();

// Автоматичне включення режиму редагування якщо поля порожні
function checkAndEnableEditMode() {
  // Перевіряємо блок з пунктом (місто та відділення)
  const cityInput = document.getElementById("nova-post-city-input");
  const warehouseSelect = document.getElementById("nova-post-warehouse-select");
  const editBtn = document.getElementById("nova-post-edit-btn");
  
  if (editBtn && cityInput && warehouseSelect) {
    // Якщо місто або відділення не заповнені - включаємо режим редагування
    if (!cityInput.value.trim() || !warehouseSelect.value) {
      editBtn.classList.add("active");
      cityInput.readOnly = false;
      if (cityInput.value.trim()) {
        warehouseSelect.disabled = false;
      }
    }
  }
  
  // Перевіряємо блок з інформацією для доставки (ім'я та телефон)
  const nameInput = document.getElementById("nova-post-name");
  const phoneInput = document.getElementById("nova-post-phone");
  const infoEditBtn = document.getElementById("nova-post-info-edit-btn");
  
  if (infoEditBtn && nameInput && phoneInput) {
    // Якщо ім'я або телефон не заповнені - включаємо режим редагування
    if (!nameInput.value.trim() || !phoneInput.value.trim()) {
      infoEditBtn.classList.add("active");
      nameInput.readOnly = false;
      phoneInput.readOnly = false;
    }
  }
}

// Відновлюємо застосований промокод при завантаженні сторінки
document.addEventListener("DOMContentLoaded", () => {
  // Перевірка порожньої корзини тепер на рівні Django template
  // checkEmptyCart(); - не потрібно, Django вже це робить
  
  restorePromocode();
  // Перевіряємо і включаємо режим редагування якщо потрібно
  checkAndEnableEditMode();
});

// Експортуємо функцію для отримання даних Нової Пошти
export { getNovaPostData };
