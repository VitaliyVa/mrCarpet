import "./index.scss";
import validation from "../../module/validation/index";

export const getFormFields = (formClassName, inputClassName) => {
  const form = document.querySelector(formClassName);
  const formInputs = form.querySelectorAll(inputClassName);

  const formState = {};

  formInputs.forEach((input) => {
    formState[input.name] = input.value;
  });

  return formState;
};

const hideAcceptModal = () => {
  const accept = document.querySelector(".modal_bad__block");
  accept.classList.remove("active");
};

const hideBadModal = () => {
  const bad = document.querySelector(".modal_bad__block");
  bad.classList.remove("active");
};

export const showLoader = () => {
  const loader = document.querySelector(".modal_loading__block");

  hideAcceptModal();
  hideBadModal();

  loader.classList.add("active");
};

export const hideLoader = () => {
  const loader = document.querySelector(".modal_loading__block");

  loader.classList.remove("active");
};

export function bad_modal(
  error_message = "Щось пішло не так, спробуйте пізніше!"
) {
  let bad = document.querySelector(".modal_bad__block");

  if (error_message) {
    remove_error();

    // код бля додавання кількох рядків помилок
    // let field_error = document.createElement("div");
    // field_error.textContent = error_message;
    // field_error.classList.add("modal_bad_text", "medium");

    // bad.append(field_error);

    bad.querySelector(".modal_bad_text").textContent = error_message;

    setTimeout(remove_error(), 3000);
  }

  setTimeout(() => {
    hideLoader();
    bad.classList.add("active");
  }, 500);

  setTimeout(() => {
    bad.classList.remove("active");
  }, 2000);
}

export function accept_modal() {
  let accept = document.querySelector(".modal_accept__block");
  let inputs = document.querySelectorAll(".validation_input");

  setTimeout(() => {
    hideLoader();
    accept.classList.add("active");
  }, 0);
  setTimeout(() => {
    accept.classList.remove("active");
  }, 4000);

  inputs.forEach((input) => (input.value = ""));
}

function remove_error() {
  let errors = document.querySelectorAll(".field_error");
  errors.forEach((error) => {
    error.remove();
  });

  let errors_modal = document.querySelectorAll(".custom_modal_text");
  errors_modal.forEach((error) => {
    error.remove();
  });
}
