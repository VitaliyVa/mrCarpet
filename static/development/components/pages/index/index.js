import "./index.scss";

document
  .querySelector(".cart_item_add_to_favorite")
  .addEventListener("click", (e) => {
    e.preventDefault();
    console.log("add_to_favorite");
  });
