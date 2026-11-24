import { trackEvent } from "../../../utils/analytics";

const filters = document.querySelector(".catalog_inside_filter");

document.addEventListener("click", ({ target }) => {
  if (target.closest(".catalog_inside_filter-btn")) {
    filters.classList.add("active");
  }

  if (target.closest(".catalog_inside_filter-close-btn")) {
    filters.classList.remove("active");
  }
});

// ---- analytics: which filters people touch, and dead ends -----------------
// filter_use per ticked/unticked value, debounced so a run of quick clicks on
// one filter is one event with the final state. Values are the visible label
// ("80x150", "Сірий"), not ids, so the report reads without a lookup.
const form = document.getElementById("filters-form");
const listId = window.location.pathname;

function labelText(input) {
  const label = input.closest("label");
  const text = (label ? label.textContent : input.value) || "";
  // "80x150 (12)" → "80x150": the count changes with other filters.
  return text.replace(/\(\d+\)\s*$/, "").replace(/\s+/g, " ").trim().slice(0, 100);
}

if (form) {
  const pending = new Map();
  form.addEventListener("change", (event) => {
    const input = event.target;
    if (!(input instanceof HTMLInputElement)) return;
    if (input.type === "checkbox") {
      const key = `${input.name}:${input.value}`;
      clearTimeout(pending.get(key));
      pending.set(
        key,
        setTimeout(() => {
          pending.delete(key);
          trackEvent("filter_use", {
            filter_name: input.name,
            filter_value: labelText(input),
            filter_action: input.checked ? "add" : "remove",
            item_list_id: listId,
          });
        }, 800)
      );
    } else if (input.name === "price_min" || input.name === "price_max") {
      clearTimeout(pending.get("price"));
      pending.set(
        "price",
        setTimeout(() => {
          pending.delete("price");
          const min = form.querySelector('[name="price_min"]');
          const max = form.querySelector('[name="price_max"]');
          trackEvent("filter_use", {
            filter_name: "price",
            filter_value: `${min?.value || ""}-${max?.value || ""}`,
            filter_action: "set",
            item_list_id: listId,
          });
        }, 800)
      );
    }
  });
}

// Landed on a filtered/sorted list that shows nothing: the shop has no answer.
const list = document.querySelector(".catalog_section_bottom[data-ga-list-id]");
if (list && list.dataset.gaResults === "0") {
  const params = new URLSearchParams(window.location.search);
  const names = [];
  params.forEach((v, k) => {
    if (v !== "" && k !== "page" && names.indexOf(k) < 0) names.push(k);
  });
  if (names.length) {
    trackEvent("filter_no_results", {
      filter_names: names.join(","),
      filter_params: decodeURIComponent(params.toString()).slice(0, 100),
      item_list_id: listId,
    });
  }
}
