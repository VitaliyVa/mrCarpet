import "./index.scss";

// «Скопіювати посилання»: clipboard API where allowed, a hidden textarea
// otherwise (older Safari, http on a local network).
const copyButton = document.querySelector("[data-share-copy]");
if (copyButton) {
  const box = copyButton.closest("[data-share-url]");
  const url = (box && box.dataset.shareUrl) || window.location.href;
  const label = copyButton.querySelector("[data-share-copy-label]");
  const initial = label ? label.textContent : "";

  const fallbackCopy = () => {
    const area = document.createElement("textarea");
    area.value = url;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    try {
      document.execCommand("copy");
    } catch (e) {
      // nothing else to try
    }
    document.body.removeChild(area);
  };

  copyButton.addEventListener("click", () => {
    const done = () => {
      copyButton.classList.add("is-copied");
      if (label) label.textContent = "Посилання скопійовано";
      setTimeout(() => {
        copyButton.classList.remove("is-copied");
        if (label) label.textContent = initial;
      }, 2200);
    };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(url).then(done, () => {
        fallbackCopy();
        done();
      });
    } else {
      fallbackCopy();
      done();
    }
  });
}

// Side table of contents: highlight the section being read.
const tocLinks = Array.from(document.querySelectorAll("[data-toc-link]"));
if (tocLinks.length && "IntersectionObserver" in window) {
  const byId = new Map(tocLinks.map((link) => [link.dataset.tocLink, link]));
  const headings = Array.from(byId.keys())
    .map((id) => document.getElementById(id))
    .filter(Boolean);

  const setActive = (id) => {
    tocLinks.forEach((link) =>
      link.classList.toggle("is-active", link.dataset.tocLink === id)
    );
  };

  const observer = new IntersectionObserver(
    (entries) => {
      const visible = entries
        .filter((entry) => entry.isIntersecting)
        .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
      if (visible.length) setActive(visible[0].target.id);
    },
    { rootMargin: "0px 0px -65% 0px", threshold: 0 }
  );
  headings.forEach((heading) => observer.observe(heading));
}

// The inline (mobile) contents closes after a jump, so it does not sit
// open above the section the reader just picked.
const inlineToc = document.querySelector(".bl-toc--inline");
if (inlineToc) {
  inlineToc.addEventListener("click", (event) => {
    if (event.target.closest("a")) inlineToc.removeAttribute("open");
  });
}
