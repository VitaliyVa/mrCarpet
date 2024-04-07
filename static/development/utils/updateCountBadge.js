export const updateCountBadge = (badgeClassName, count = "???") => {
  const badgeElements = document.querySelectorAll(badgeClassName);

  if (badgeElements.length) {
    badgeElements.forEach((badge) => {
      const badgeCountLabel = badge.querySelector(
        ".header_bottom_panel_item_count"
      );

      if (badgeCountLabel) {
        badgeCountLabel.textContent = count;
      }
    });
  }
};
