const phoneInputs = document.querySelectorAll('[data-type="phone"]');

phoneInputs.forEach((element) => {
  element.addEventListener("input", handleInput, false);
});

function handleInput(e) {
  e.target.value = phoneMask(e.target.value);
}

function phoneMask(phone) {
  return phone
    .replace(/\D/g, "")
    .replace(/^(\d)/, "($1")
    .replace(/^(\(\d{3})(\d)/, "$1) $2")
    .replace(/(\d{2})(\d{2})/, "$1-$2")
    .replace(/(-\d{7})\d+?$/, "$1");
}
