// Delivery cost and the "до безкоштовної доставки ще N грн." hint in the
// cart / checkout summary. Called after a promocode and after every cart
// change (quantity, delete), so the block never shows a stale total.
export function updateFreeShippingUI(fs, finalPrice) {
  const root = document.getElementById("basket-delivery-cost");
  const priceEl = document.getElementById("basket-delivery-price");
  const hintEl = document.getElementById("basket-delivery-hint");
  if (!root || !priceEl) return;

  const enabled =
    fs?.enabled ?? root.dataset.fsEnabled === "1";
  const threshold = Number(fs?.threshold ?? root.dataset.fsThreshold ?? 0);
  const fromPrice = Number(fs?.delivery_from_price ?? root.dataset.fsFrom ?? 90);
  const total = Number(finalPrice);
  const qualifies =
    fs?.qualifies ?? (enabled && threshold > 0 && total >= threshold);
  const remaining =
    fs?.remaining ??
    (enabled && !qualifies ? Math.max(0, threshold - Math.round(total)) : 0);

  root.dataset.fsEnabled = enabled ? "1" : "0";
  root.dataset.fsThreshold = String(threshold);
  root.dataset.fsFrom = String(fromPrice);

  if (qualifies) {
    priceEl.classList.add("is-free");
    priceEl.innerHTML = `
      <span class="basket__calculate-delivery-was">Від ${fromPrice} грн.</span>
      <span class="basket__calculate-delivery-now">Безкоштовно</span>
    `;
    // "Безкоштовно" next to the struck price already says it: no extra line.
    if (hintEl) {
      hintEl.hidden = true;
      hintEl.textContent = "";
    }
  } else {
    priceEl.classList.remove("is-free");
    priceEl.innerHTML = `
      <span class="basket__calculate-delivery-carrier">${fromPrice > 0 ? `Від ${fromPrice} грн.` : "за тарифами Нової Пошти"}</span>
    `;
    if (hintEl) {
      if (enabled && remaining > 0) {
        hintEl.hidden = false;
        hintEl.classList.remove("is-free");
        hintEl.textContent = `До безкоштовної доставки ще ${remaining} грн.`;
      } else {
        hintEl.hidden = true;
        hintEl.textContent = "";
      }
    }
  }

  const npPrice = document.getElementById("nova-post-delivery-price");
  if (npPrice) {
    if (qualifies) {
      npPrice.classList.add("is-free");
      npPrice.innerHTML = `
        <span class="basket__checkbox-item-price-was">Від ${fromPrice} грн.</span>
        <span class="basket__checkbox-item-price-now">Безкоштовно</span>
      `;
    } else {
      npPrice.classList.remove("is-free");
      npPrice.textContent = `Від ${fromPrice} грн.`;
    }
  }
}
