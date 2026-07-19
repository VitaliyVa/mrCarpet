import { getProductsBySearchQuery } from "../../../api/search";
import { trackEvent } from "../../../utils/analytics";

const searchInput = document.querySelector(".header__search input");
const searchBody = document.querySelector(".header__search-body");
const searchBodyResults = searchBody?.querySelector(".header__search-items");

let searchTimer = null;
let lastTrackedQuery = "";

/** Escape text for safe use inside HTML attribute/text contexts. */
function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** Only allow http(s) or site-relative URLs in search result links/images. */
function safeUrl(value, { allowRelative = true } = {}) {
  const raw = String(value ?? "").trim();
  if (!raw) return allowRelative ? "#" : "";
  if (allowRelative && raw.startsWith("/") && !raw.startsWith("//")) {
    return raw;
  }
  try {
    const u = new URL(raw, window.location.origin);
    if (u.protocol === "http:" || u.protocol === "https:") {
      return u.href;
    }
  } catch {
    /* ignore */
  }
  return allowRelative ? "#" : "";
}

function renderSearchItem({ id, title, image, image_url, href }) {
  const safeId = escapeHtml(id);
  const safeTitle = escapeHtml(title);
  const safeHref = escapeHtml(safeUrl(href));
  // API: ProductSerializer → image_url; /catalog/api/search/ → image
  const safeImage = escapeHtml(safeUrl(image_url || image));

  return `
<div class="header__search-product" data-product-id="${safeId}" data-catalog-product-id="${safeId}" data-product-title="${safeTitle}">
  <div class="header__search-product-left">
    <div class="header__search-product-img">
      <a href="${safeHref}">
        <img src="${safeImage}" alt="${safeTitle}" />
      </a>
    </div>
    <div class="header__search-product-info">
      <a href="${safeHref}">
        <h4 class="header__search-product-title">${safeTitle}</h4>
      </a>
    </div>
  </div>
</div>`;
}

const renderSearchResults = (searchResults) => {
  if (!searchBodyResults) return;

  if (!Array.isArray(searchResults) || !searchResults.length) {
    searchBodyResults.textContent = "";
    const empty = document.createElement("p");
    empty.className = "header__search-text";
    empty.textContent = "Товарів не знайдено 🥲";
    searchBodyResults.appendChild(empty);
    return;
  }

  // Titles/URLs escaped above; still avoid joining untrusted raw HTML.
  searchBodyResults.innerHTML = searchResults.map(renderSearchItem).join("");
};

const onSearch = async () => {
  let findedProducts = [];
  const query = (searchInput?.value || "").trim();

  if (query.length) {
    findedProducts = (await getProductsBySearchQuery(query)) || [];
  }

  renderSearchResults(findedProducts);

  if (query.length >= 2 && query !== lastTrackedQuery) {
    lastTrackedQuery = query;
    trackEvent("search", {
      search_term: query.slice(0, 100),
      results_count: findedProducts.length,
    });
  }
};

if (searchInput) {
  searchInput.addEventListener("input", () => {
    searchBody?.classList.add("active");
    clearTimeout(searchTimer);
    searchTimer = setTimeout(onSearch, 500);
  });
}

if (searchBody) {
  document.addEventListener("click", ({ target }) => {
    if (target.closest(".header__search-head")) {
      searchBody.classList.toggle("active");
    }
    if (!target.closest(".header")) {
      searchBody.classList.remove("active");
    }
  });
}
