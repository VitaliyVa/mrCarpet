// Nova Post API Integration
import IMask from "imask";
import Choices from "choices.js";

let selectedSettlement = null;
let selectedWarehouse = null;
let searchTimeout = null;
let phoneMask = null;
let warehouseChoices = null;

// Ініціалізація функціоналу Нової Пошти
export function initNovaPost() {
  const cityInput = document.getElementById("nova-post-city-input");
  const cityDropdown = document.getElementById("nova-post-city-dropdown");
  const warehouseSelect = document.getElementById("nova-post-warehouse-select");
  const editBtn = document.getElementById("nova-post-edit-btn");
  const phoneInput = document.getElementById("nova-post-phone");

  if (!cityInput || !cityDropdown || !warehouseSelect || !editBtn) {
    return;
  }

  // Ініціалізація маски для телефону
  if (phoneInput && !phoneMask) {
    phoneMask = IMask(phoneInput, {
      mask: "+{38\\0} 00 000 00 00",
      lazy: false,
    });
  }

  // Ініціалізація Choices.js для селекту відділень
  if (warehouseSelect && !warehouseChoices) {
    warehouseChoices = new Choices(warehouseSelect, {
      searchEnabled: true,
      searchPlaceholderValue: "Пошук відділення...",
      noResultsText: "Нічого не знайдено",
      itemSelectText: "", // Забираємо текст "Натисніть для вибору"
      shouldSort: false,
      removeItemButton: false,
      placeholderValue: "Оберіть відділення",
    });
  }

  // Обробка кнопки редагування
  editBtn.addEventListener("click", function (e) {
    e.preventDefault();
    const bodyBlock = editBtn.closest(".basket__checkbox-item-body-block");
    const fields = bodyBlock.querySelectorAll("input, select");

    if (editBtn.classList.contains("active")) {
      // Завершення редагування
      editBtn.classList.remove("active");
      fields.forEach((field) => {
        field.readOnly = true;
        if (field.tagName === "SELECT") {
          field.disabled = true;
        }
      });
    } else {
      // Початок редагування
      editBtn.classList.add("active");
      fields.forEach((field) => {
        field.readOnly = false;
        if (field.tagName === "SELECT" && selectedSettlement) {
          field.disabled = false;
        }
      });
      cityInput.focus();
    }
  });

  // Пошук міста з дебаунсом
  cityInput.addEventListener("input", function () {
    let query = cityInput.value.trim();
    
    // Автоматично робимо першу букву великою
    if (query.length > 0) {
      query = query.charAt(0).toUpperCase() + query.slice(1);
      cityInput.value = query;
    }

    clearTimeout(searchTimeout);

    if (query.length < 2) {
      cityDropdown.style.display = "none";
      return;
    }

    searchTimeout = setTimeout(() => {
      searchSettlements(query);
    }, 300);
  });

  // Закриття випадаючого списку при кліку поза ним
  document.addEventListener("click", function (e) {
    if (
      !cityInput.contains(e.target) &&
      !cityDropdown.contains(e.target)
    ) {
      cityDropdown.style.display = "none";
    }
  });

  // Обробка зміни відділення через Choices.js
  if (warehouseSelect) {
    warehouseSelect.addEventListener("change", function (event) {
      const value = event.target.value;
      
      if (value && warehouseChoices) {
        // Отримуємо вибрану опцію з customProperties
        const selectedChoice = warehouseChoices._currentState.choices.find(
          choice => choice.value === value
        );
        
        if (selectedChoice && selectedChoice.customProperties) {
          selectedWarehouse = {
            id: value,
            title: selectedChoice.customProperties.title,
            ref: selectedChoice.customProperties.ref,
          };
        }
      }
    });
  }
}

// Пошук населених пунктів
async function searchSettlements(query) {
  const cityDropdown = document.getElementById("nova-post-city-dropdown");

  try {
    cityDropdown.innerHTML = '<div class="nova-post-dropdown-item loading">Завантаження...</div>';
    cityDropdown.style.display = "block";

    const response = await fetch(`/api/settlements/?q=${encodeURIComponent(query)}`);
    const data = await response.json();

    if (data.results && data.results.length > 0) {
      renderSettlements(data.results);
    } else {
      cityDropdown.innerHTML = '<div class="nova-post-dropdown-item no-results">Нічого не знайдено</div>';
    }
  } catch (error) {
    console.error("Помилка при пошуку міста:", error);
    cityDropdown.innerHTML = '<div class="nova-post-dropdown-item error">Помилка завантаження</div>';
  }
}

// Відображення списку населених пунктів
function renderSettlements(settlements) {
  const cityDropdown = document.getElementById("nova-post-city-dropdown");
  const cityInput = document.getElementById("nova-post-city-input");

  cityDropdown.innerHTML = "";

  settlements.forEach((settlement) => {
    const item = document.createElement("div");
    item.className = "nova-post-dropdown-item";
    item.textContent = settlement.title;
    item.dataset.id = settlement.id;
    item.dataset.ref = settlement.ref;
    item.dataset.title = settlement.title;

    item.addEventListener("click", function () {
      selectedSettlement = {
        id: settlement.id,
        ref: settlement.ref,
        title: settlement.title,
      };

      cityInput.value = settlement.title;
      cityDropdown.style.display = "none";

      // Завантажуємо відділення для обраного міста
      loadWarehouses(settlement.ref);
    });

    cityDropdown.appendChild(item);
  });

  cityDropdown.style.display = "block";
}

// Завантаження відділень
async function loadWarehouses(settlementRef) {
  const warehouseWrapper = document.querySelector(".nova-post-warehouse-wrapper");
  const loadingIndicator = document.getElementById("warehouse-loading");

  try {
    // Показуємо індикатор завантаження
    if (loadingIndicator) {
      loadingIndicator.style.display = "flex";
    }
    if (warehouseWrapper) {
      warehouseWrapper.classList.add("loading");
    }

    // Очищаємо селект через Choices.js
    if (warehouseChoices) {
      warehouseChoices.clearChoices();
      warehouseChoices.setChoices([
        { value: "", label: "Завантаження...", disabled: true },
      ], "value", "label", true);
      warehouseChoices.disable();
    }

    const response = await fetch(`/api/warehouses/?q=${encodeURIComponent(settlementRef)}`);
    const data = await response.json();

    if (data.results && data.results.length > 0) {
      renderWarehouses(data.results);
    } else {
      if (warehouseChoices) {
        warehouseChoices.clearChoices();
        warehouseChoices.setChoices([
          { value: "", label: "Відділення не знайдено", disabled: true },
        ], "value", "label", true);
      }
    }
  } catch (error) {
    console.error("Помилка при завантаженні відділень:", error);
    if (warehouseChoices) {
      warehouseChoices.clearChoices();
      warehouseChoices.setChoices([
        { value: "", label: "Помилка завантаження", disabled: true },
      ], "value", "label", true);
    }
  } finally {
    // Ховаємо індикатор завантаження
    if (loadingIndicator) {
      loadingIndicator.style.display = "none";
    }
    if (warehouseWrapper) {
      warehouseWrapper.classList.remove("loading");
    }
  }
}

// Відображення списку відділень
function renderWarehouses(warehouses) {
  if (warehouseChoices) {
    // Очищаємо попередні варіанти
    warehouseChoices.clearChoices();
    
    // Додаємо placeholder
    const choices = [
      { value: "", label: "Оберіть відділення", placeholder: true },
    ];
    
    // Додаємо відділення
    warehouses.forEach((warehouse) => {
      choices.push({
        value: warehouse.id,
        label: warehouse.title,
        customProperties: {
          title: warehouse.title,
          ref: warehouse.ref,
          shortAddress: warehouse.short_address,
        },
      });
    });
    
    warehouseChoices.setChoices(choices, "value", "label", true);
    warehouseChoices.enable();
  }
}

// Отримання обраних даних для відправки замовлення
export function getNovaPostData() {
  return {
    settlement: selectedSettlement,
    warehouse: selectedWarehouse,
  };
}

