import "./index.scss";
import validation from "../../module/validation/index";

// form_send(".sign-in__form");
// form_send(".register-modal__form");

export const getFormFields = (formClassName, inputClassName) => {
  const form = document.querySelector(formClassName);
  const formInputs = form.querySelectorAll(inputClassName);

  const formState = {};

  formInputs.forEach((input) => {
    formState[input.name] = input.value;
  });

  return formState;
};

// function form_send(wrapper, modal) {
//   let form_wrapper = document.querySelectorAll(wrapper);
//   let loader = document.querySelector(".modal_loading__block");
//   form_wrapper.forEach((element) => {
//     let action = element.getAttribute("action");
//     let btn = element.querySelector(".validation_btn");

//     if (btn != null) {
//       btn.addEventListener("click", function (e) {
//         e.preventDefault();
//         // функція для валідації при кліці на кнопку
//         let status = validation(btn);

//         // console.log(status);

//         // if (status == true) {
//         //   console.log("send!");
//         //   let elements = element.elements;
//         //   let obj = {};
//         //   for (let i = 0; i < elements.length; i++) {
//         //     let item = elements.item(i);
//         //     let check_type = ["file", "reset", "submit", "button"].indexOf(
//         //       item.type
//         //     );
//         //     if (check_type > -1) {
//         //     } else {
//         //       obj[item.name] = item.value;
//         //     }
//         //   }
//         //   // const item = document.querySelector(wrapper);
//         //   // obj["item_id"] = item.dataset.id;
//         //   // if (item.dataset.count) {
//         //   //   obj["count"] = item.dataset.count;
//         //   // }

//         //   // переписати або написати нову

//         //   // if (action) {
//         //   //   loader.classList.add("active");
//         //   //   const cookie = document.cookie;
//         //   //   const csrfKey = "csrftoken=";
//         //   //   const start = cookie.indexOf(csrfKey);
//         //   //   const end = cookie.indexOf(";", start);
//         //   //   const csrf = cookie.slice(start + csrfKey.length, end);
//         //   //   fetch(action, {
//         //   //     method: "POST",
//         //   //     body: new URLSearchParams(obj),
//         //   //     headers: {
//         //   //       "X-CSRFToken": csrf,
//         //   //     },
//         //   //     // body: new URLSearchParams(obj).toString(),
//         //   //   })
//         //   //     .then((data) => {
//         //   //       console.log("data1: ", data);
//         //   //       if (data?.res?.ok) {
//         //   //         accept_modal();
//         //   //       }
//         //   //       return data.json();
//         //   //     })
//         //   //     .then((res) => {
//         //   //       console.log(res);
//         //   //       if (
//         //   //         (action.includes("create_user") ||
//         //   //           action.includes("login_user")) &&
//         //   //         res?.url
//         //   //       ) {
//         //   //         document.location.href = res.url;
//         //   //       } else if (
//         //   //         (action.includes("create_user") ||
//         //   //           action.includes("login_user")) &&
//         //   //         res
//         //   //       ) {
//         //   //         const error = res?.email || res?.username;
//         //   //         bad_modal(error, false);
//         //   //       }
//         //   //       if (
//         //   //         action.includes("update_user_profile") &&
//         //   //         res?.status === "OK"
//         //   //       ) {
//         //   //         document.location.reload();
//         //   //       }
//         //   //     })
//         //   //     .catch((error) => {
//         //   //       console.log("error: ", error);
//         //   //       bad_modal(error);
//         //   //     })
//         //   //     .finally(() => {
//         //   //       loader.classList.remove("active");
//         //   //     });
//         //   // }
//         // } else {
//         //   console.log("error!");
//         // }
//       });
//     } else {
//       console.error(
//         `такого модального вікна не існує на цій сторінці - ${wrapper}`
//       );
//     }
//   });
// }

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

export function bad_modal(error_message, addedDefaultText = true) {
  let bad = document.querySelector(".modal_bad__block");

  if (error_message) {
    remove_error();

    console.log("error_message: ", error_message);
    let field_error = document.createElement("div");
    field_error.textContent = error_message;
    field_error.classList.add(
      "custom_modal_text",
      "modal_bad_text",
      "bold_title",
      "bold_title_2",
      "color_red"
    );
    console.log("field_error: ", field_error);

    bad.append(field_error);

    if (addedDefaultText) {
      bad.querySelector(".modal_bad_text").textContent =
        "Щось пішло не так, спробуйте пізніше!";
    } else {
      bad.querySelector(".modal_bad_text").textContent = "";
    }
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
