// Nova Post API Integration
import IMask from "imask";
import Choices from "choices.js";
import "choices.js/public/assets/styles/choices.min.css";

let selectedSettlement = null;
let selectedWarehouse = null;
let searchTimeout = null;
let phoneMask = null;
let warehouseChoices = null;

export function initNovaPost() {
  const cityInput = document.getElementById("nova-post-city-input");
  const cityDropdown = document.getElementById("nova-post-city-dropdown");
  const warehouseSelect = document.getElementById("nova-post-warehouse-select");
  const phoneInput = document.getElementById("nova-post-phone");

  if (!cityInput || !cityDropdown || !warehouseSelect) {
    return;
  }

  if (phoneInput && !phoneMask) {
    phoneMask = IMask(phoneInput, {
      mask: "+{38\\0} 00 000 00 00",
      lazy: false,
    });
  }

  if (!warehouseChoices) {
    warehouseChoices = new Choices(warehouseSelect, {
      searchEnabled: true,
      searchPlaceholderValue: "Пошук відділення...",
      noResultsText: "Нічого не знайдено",
      itemSelectText: "",
      shouldSort: false,
      removeItemButton: false,
      placeholder: true,
      placeholderValue: "Спочатку оберіть місто",
      allowHTML: false,
    });
    warehouseChoices.disable();
  }

  cityInput.addEventListener("input", function () {
    let query = cityInput.value.trim();

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

  document.addEventListener("click", function (e) {
    if (!cityInput.contains(e.target) && !cityDropdown.contains(e.target)) {
      cityDropdown.style.display = "none";
    }
  });

  warehouseSelect.addEventListener("change", function (event) {
    const value = event.target.value;

    if (value && warehouseChoices) {
      const selectedChoice = warehouseChoices._currentState.choices.find(
        (choice) => choice.value === value
      );

      if (selectedChoice && selectedChoice.customProperties) {
        selectedWarehouse = {
          id: value,
          title: selectedChoice.customProperties.title,
          ref: selectedChoice.customProperties.ref,
        };
      }
    } else {
      selectedWarehouse = null;
    }
  });
}

async function searchSettlements(query) {
  const cityDropdown = document.getElementById("nova-post-city-dropdown");

  try {
    cityDropdown.innerHTML =
      '<div class="nova-post-dropdown-item loading">Завантаження...</div>';
    cityDropdown.style.display = "block";

    const response = await fetch(
      `/api/settlements/?q=${encodeURIComponent(query)}`
    );
    const data = await response.json();

    if (data.results && data.results.length > 0) {
      renderSettlements(data.results);
    } else {
      cityDropdown.innerHTML =
        '<div class="nova-post-dropdown-item no-results">Нічого не знайдено</div>';
    }
  } catch (error) {
    console.error("Помилка при пошуку міста:", error);
    cityDropdown.innerHTML =
      '<div class="nova-post-dropdown-item error">Помилка завантаження</div>';
  }
}

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
      selectedWarehouse = null;

      cityInput.value = settlement.title;
      cityDropdown.style.display = "none";

      loadWarehouses(settlement.ref);
    });

    cityDropdown.appendChild(item);
  });

  cityDropdown.style.display = "block";
}

async function loadWarehouses(settlementRef, selectWarehouseId = null) {
  const warehouseWrapper = document.querySelector(".nova-post-warehouse-wrapper");
  const loadingIndicator = document.getElementById("warehouse-loading");

  try {
    if (loadingIndicator) {
      loadingIndicator.style.display = "flex";
    }
    if (warehouseWrapper) {
      warehouseWrapper.classList.add("loading");
    }

    if (warehouseChoices) {
      warehouseChoices.clearStore();
      warehouseChoices.setChoices(
        [{ value: "", label: "Завантаження...", disabled: true, selected: true }],
        "value",
        "label",
        true
      );
      warehouseChoices.disable();
    }

    const response = await fetch(
      `/api/warehouses/?q=${encodeURIComponent(settlementRef)}`
    );
    const data = await response.json();

    if (data.results && data.results.length > 0) {
      renderWarehouses(data.results, selectWarehouseId);
    } else if (warehouseChoices) {
      warehouseChoices.clearStore();
      warehouseChoices.setChoices(
        [
          {
            value: "",
            label: "Відділення не знайдено",
            disabled: true,
            selected: true,
          },
        ],
        "value",
        "label",
        true
      );
      warehouseChoices.disable();
    }
  } catch (error) {
    console.error("Помилка при завантаженні відділень:", error);
    if (warehouseChoices) {
      warehouseChoices.clearStore();
      warehouseChoices.setChoices(
        [
          {
            value: "",
            label: "Помилка завантаження",
            disabled: true,
            selected: true,
          },
        ],
        "value",
        "label",
        true
      );
      warehouseChoices.disable();
    }
  } finally {
    if (loadingIndicator) {
      loadingIndicator.style.display = "none";
    }
    if (warehouseWrapper) {
      warehouseWrapper.classList.remove("loading");
    }
  }
}

function renderWarehouses(warehouses, selectWarehouseId = null) {
  if (!warehouseChoices) {
    return;
  }

  const selectId = selectWarehouseId ? String(selectWarehouseId) : "";
  let matched = null;

  const choices = [
    {
      value: "",
      label: "Оберіть відділення",
      placeholder: true,
      selected: !selectId,
    },
  ];

  warehouses.forEach((warehouse) => {
    const value = String(warehouse.id);
    const isSelected = Boolean(selectId && value === selectId);
    if (isSelected) {
      matched = warehouse;
    }
    choices.push({
      value,
      label: warehouse.title,
      selected: isSelected,
      customProperties: {
        title: warehouse.title,
        ref: warehouse.ref,
        shortAddress: warehouse.short_address,
      },
    });
  });

  warehouseChoices.clearStore();
  warehouseChoices.setChoices(choices, "value", "label", true);
  warehouseChoices.enable();

  if (matched) {
    warehouseChoices.setChoiceByValue(String(matched.id));
    selectedWarehouse = {
      id: String(matched.id),
      title: matched.title,
      ref: matched.ref,
    };
  } else if (selectId) {
    // збережене відділення вже не в списку — лишаємо текстовий fallback у state
    selectedWarehouse = {
      id: selectId,
      title: selectedWarehouse?.title || "",
      ref: selectedWarehouse?.ref || "",
    };
  }
}

/**
 * Автозаповнення з профілю користувача (місто + відділення + контакти).
 */
export async function prefillNovaPost(data = {}) {
  const cityInput = document.getElementById("nova-post-city-input");
  const nameInput = document.getElementById("nova-post-name");
  const emailInput = document.getElementById("nova-post-email");
  const phoneInput = document.getElementById("nova-post-phone");

  if (!cityInput) return;

  if (data.name && nameInput && !nameInput.value.trim()) {
    nameInput.value = data.name;
  }
  if (data.email && emailInput && !emailInput.value.trim()) {
    emailInput.value = data.email;
  }
  if (data.phone && phoneInput) {
    if (phoneMask) {
      phoneMask.value = data.phone;
    } else if (!phoneInput.value.trim()) {
      phoneInput.value = data.phone;
    }
  }

  const city = (data.city || "").trim();
  const settlementRef = (data.settlementRef || "").trim();
  if (!city) return;

  cityInput.value = city;
  selectedSettlement = {
    id: null,
    ref: settlementRef,
    title: city,
  };

  if (data.warehouseTitle || data.warehouseRef || data.warehouseId) {
    selectedWarehouse = {
      id: data.warehouseId ? String(data.warehouseId) : "",
      title: data.warehouseTitle || "",
      ref: data.warehouseRef || "",
    };
  }

  if (settlementRef) {
    await loadWarehouses(settlementRef, data.warehouseId || null);
  }
}

export function getNovaPostData() {
  return {
    settlement: selectedSettlement,
    warehouse: selectedWarehouse,
  };
}
