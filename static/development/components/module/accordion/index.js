import "./index.scss";

document.querySelectorAll(".accordion_content__block").forEach((block) => {
  block.addEventListener("click", (e) => {
    const content = block.querySelector(".accordion_content");
    if (content && content.contains(e.target)) return;

    block.classList.toggle("active");
  });
});
