import "./index.scss";
import IMask from "imask";
import Cookies from "js-cookie";
import axios from "axios";
import { showSuccess, showError } from "../../../utils/notifications";

let phoneMask = null;

function isInStockLabel(label) {
  return label?.dataset?.inStock === "1";
}

function getActiveSizeLabel(root) {
  return root?.querySelector(".sizes-block .size-label.active");
}

export function syncStockUI(root) {
  if (!root) return;

  const active = getActiveSizeLabel(root);
  const inStock = active ? isInStockLabel(active) : true;

  const oosBadge =
    root.querySelector(".cart_item_oos") || root.querySelector(".product_oos");
  if (oosBadge) {
    oosBadge.classList.toggle("is-visible", !inStock);
  }

  const bagBtn = root.querySelector(".cart_item__add-to-cart-btn");
  if (bagBtn) {
    bagBtn.dataset.action = inStock ? "cart" : "inquire";
    bagBtn.title = inStock ? "Додати до кошика" : "Дізнатись про наявність";
    bagBtn.hidden = false;
  }

  const addBtn = root.querySelector(".add-to-cart");
  const askBtn = root.querySelector(".ask-availability");
  if (addBtn) addBtn.hidden = !inStock;
  if (askBtn) askBtn.hidden = inStock;

  const option = root.querySelector(".product__option");
  if (option) {
    option.classList.toggle("is-oos", !inStock);
  }
}

export function initStockAvailability() {
  document.querySelectorAll(".cart_item, .product").forEach((root) => {
    syncStockUI(root);
  });
}

function openStockInquiryModal(payload) {
  const modal = document.querySelector(".stock-inquiry-modal");
  if (!modal) return;

  const overlay = modal.closest(".modal-overlay");
  document.querySelectorAll(".modal__block.active").forEach((m) => {
    m.classList.remove("active");
    m.closest(".modal-overlay")?.classList.remove("active");
  });

  document.getElementById("stock-inquiry-product-id").value =
    payload.catalogProductId || "";
  document.getElementById("stock-inquiry-attr-id").value =
    payload.attrId || "";
  document.getElementById("stock-inquiry-product-title").value =
    payload.productTitle || "";
  document.getElementById("stock-inquiry-size").value = payload.sizeLabel || "";

  const errorEl = document.getElementById("stock-inquiry-error");
  if (errorEl) {
    errorEl.hidden = true;
    errorEl.textContent = "";
    errorEl.style.color = "#dc3545";
  }

  const phoneInput = document.getElementById("stock-inquiry-phone");
  if (phoneInput && !phoneMask) {
    phoneMask = IMask(phoneInput, {
      mask: "+{38\\0} 00 000 00 00",
      lazy: false,
    });
  }

  modal.classList.add("active");
  overlay?.classList.add("active");
  document.body.style.overflowY = "hidden";
}

function collectInquiryPayloadFromRoot(root) {
  if (!root) return null;
  const active = getActiveSizeLabel(root);
  const title =
    root.dataset.productTitle ||
    root.querySelector(".cart_item_title a, .product__right h1, .title h1")
      ?.textContent?.trim() ||
    "";

  return {
    catalogProductId: root.dataset.catalogProductId || "",
    attrId: active?.dataset?.item || root.dataset.productId || "",
    productTitle: title,
    sizeLabel: active?.dataset?.size || active?.textContent?.trim() || "",
  };
}

document.addEventListener("click", ({ target }) => {
  const askBtn = target.closest(".ask-availability");
  if (askBtn) {
    const root = askBtn.closest(".product") || askBtn.closest(".cart_item");
    const payload = collectInquiryPayloadFromRoot(root);
    if (payload) openStockInquiryModal(payload);
  }
});

document.addEventListener("open-stock-inquiry", (e) => {
  const root = e.target.closest?.(".cart_item") || e.target;
  const payload = collectInquiryPayloadFromRoot(root);
  if (payload) openStockInquiryModal(payload);
});

document.addEventListener("DOMContentLoaded", () => {
  initStockAvailability();

  const form = document.getElementById("stock-inquiry-form");
  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const errorEl = document.getElementById("stock-inquiry-error");
    const submitBtn = document.getElementById("stock-inquiry-submit");

    const name = document.getElementById("stock-inquiry-name").value.trim();
    const email = document.getElementById("stock-inquiry-email").value.trim();
    const phone = document.getElementById("stock-inquiry-phone").value.trim();
    const productAttrId = document.getElementById("stock-inquiry-attr-id").value;
    const productId = document.getElementById("stock-inquiry-product-id").value;
    const productTitle = document.getElementById(
      "stock-inquiry-product-title"
    ).value;
    const sizeLabel = document.getElementById("stock-inquiry-size").value;

    const phoneDigits = phone.replace(/\D/g, "");
    if (!name || !email || phoneDigits.length < 12 || !productAttrId) {
      showError("Заповніть ім’я, телефон і email коректно.");
      return;
    }

    const closeModal = () => {
      form.reset();
      if (errorEl) {
        errorEl.hidden = true;
        errorEl.textContent = "";
      }
      document
        .querySelector(".stock-inquiry-modal")
        ?.classList.remove("active");
      document
        .querySelector(".stock-inquiry-modal")
        ?.closest(".modal-overlay")
        ?.classList.remove("active");
      document.body.style.overflowY = "initial";
    };

    submitBtn.disabled = true;
    const original = submitBtn.textContent;
    submitBtn.textContent = "Надсилаємо…";

    try {
      await axios.post(
        "/api/stock-inquiry/",
        {
          name,
          email,
          phone,
          product_attr_id: Number(productAttrId),
          product_id: productId ? Number(productId) : null,
          product_title: productTitle,
          size_label: sizeLabel,
        },
        {
          headers: {
            "X-CSRFToken": Cookies.get("csrftoken"),
            "Content-Type": "application/json",
          },
        }
      );

      closeModal();
      showSuccess("Запит надіслано. Ми скоро з вами зв’яжемось.");
    } catch (err) {
      closeModal();
      const data = err?.response?.data;
      showError(
        data?.message ||
          data?.email?.[0] ||
          data?.phone?.[0] ||
          data?.detail ||
          "Не вдалося надіслати. Спробуйте ще раз."
      );
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = original;
    }
  });
});
