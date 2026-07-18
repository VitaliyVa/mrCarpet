import { subscribeToNewsletter } from "../../../api/subscription";
import { getFormFields } from "../../module/form_action";
import validation from "../../module/validation";
import "./welcome-promo-modal.scss";

const WELCOME_PROMO_FALLBACK = "WELCOME5";
const HIGHLIGHT_MS = 2800;

const subscribeButton = document.querySelector(".subscribe-btn");

export function highlightNewsletterSubscribe() {
  const form = document.getElementById("newsletter-subscribe");
  if (!form) return;

  form.classList.add("is-highlighted");
  window.clearTimeout(form._newsletterHighlightTimer);
  form._newsletterHighlightTimer = window.setTimeout(() => {
    form.classList.remove("is-highlighted");
  }, HIGHLIGHT_MS);
}

function closeWelcomePromoModal() {
  const modal = document.querySelector(".welcome-promo-modal");
  const overlay = modal?.closest(".modal-overlay");
  if (!modal || !overlay) return;

  modal.classList.remove("active");
  overlay.classList.remove("active");
  document.body.style.overflowY = "initial";
}

export function openWelcomePromoModal(code = WELCOME_PROMO_FALLBACK) {
  const modal = document.querySelector(".welcome-promo-modal");
  const overlay = modal?.closest(".modal-overlay");
  const codeEl = modal?.querySelector("[data-welcome-promo-code]");
  const hintEl = modal?.querySelector("[data-welcome-promo-hint]");
  const copyBtn = modal?.querySelector("[data-welcome-promo-copy]");

  if (!modal || !overlay || !codeEl) return;

  codeEl.textContent = code || WELCOME_PROMO_FALLBACK;
  if (hintEl) hintEl.hidden = true;
  if (copyBtn) copyBtn.textContent = "Скопіювати";

  document.querySelectorAll(".modal__block.active").forEach((el) => {
    el.classList.remove("active");
    el.closest(".modal-overlay")?.classList.remove("active");
  });

  overlay.classList.add("active");
  modal.classList.add("active");
  document.body.style.overflowY = "hidden";
}

async function copyWelcomePromoCode() {
  const modal = document.querySelector(".welcome-promo-modal");
  const codeEl = modal?.querySelector("[data-welcome-promo-code]");
  const hintEl = modal?.querySelector("[data-welcome-promo-hint]");
  const copyBtn = modal?.querySelector("[data-welcome-promo-copy]");
  const code = (codeEl?.textContent || WELCOME_PROMO_FALLBACK).trim();

  try {
    await navigator.clipboard.writeText(code);
  } catch {
    const range = document.createRange();
    range.selectNodeContents(codeEl);
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    document.execCommand("copy");
    selection.removeAllRanges();
  }

  if (hintEl) hintEl.hidden = false;
  if (copyBtn) {
    copyBtn.textContent = "Скопійовано";
    window.setTimeout(() => {
      copyBtn.textContent = "Скопіювати";
    }, 2000);
  }
}

function initWelcomePromoModal() {
  const copyBtn = document.querySelector("[data-welcome-promo-copy]");
  if (copyBtn) {
    copyBtn.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      copyWelcomePromoCode();
    });
  }

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    const modal = document.querySelector(".welcome-promo-modal.active");
    if (modal) closeWelcomePromoModal();
  });
}

initWelcomePromoModal();

if (subscribeButton) {
  subscribeButton.addEventListener("click", async (event) => {
    event.preventDefault();

    const formValues = getFormFields(".subscription-form", ".validation_input");
    const status = validation(subscribeButton);

    if (!status) return;

    const data = await subscribeToNewsletter(formValues.email);
    if (!data) return;

    const code = data.welcome_promocode || WELCOME_PROMO_FALLBACK;
    openWelcomePromoModal(code);
  });
}
