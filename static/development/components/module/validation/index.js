import validator from "validator";
import "./index.scss";

export default function validation(validation_btn) {
  // validation_btn - кнопка форми яка відправляє дані

  // змінна для зберігання помилок
  let count_error = 0;

  // змінна де зберігаються всі типи інпутів з текстом помилки та перевірками
  let input_type = {
    required: {
      error: {
        ua: "Це поле обов'язкове для заповнення!",
        ru: "Це поле обов'язкове для заповнення!",
        eng: "This field is required!",
      },
      check: (value) => {
        if (value.length != 0) {
          return true;
        } else {
          return false;
        }
      },
    },
    email: {
      error: {
        ua: "Пошта введена невірно!",
        ru: "Почта введена невірно!",
        eng: "Mail entered incorrectly!",
      },
      check: validator.isEmail,
    },
    name: {
      error: {
        ua: "Ім'я введено невірно!",
        ru: "Ім'я введено невірно!",
        eng: "The name was entered incorrectly!",
      },
      check: (value) => {
        let check = validator.isNumeric(value);
        console.log("check: ", check);
        if (!check) {
          return true;
        } else {
          return false;
        }
      },
    },
    phone: {
      error: {
        ua: "Номер телефону введено невірно!",
        ru: "Телефон введено невірно!",
        eng: "The phone was entered incorrectly!",
      },
      check: (value) => {
        return validator.isStrongPassword(value, {
          minLength: 1,
          minLowercase: 0,
          minUppercase: 0,
          minNumbers: 0,
          minSymbols: 0,
          returnScore: false,
          pointsPerUnique: 0,
          pointsPerRepeat: 0,
          pointsForContainingLower: 0,
          pointsForContainingUpper: 0,
          pointsForContainingNumber: 0,
          pointsForContainingSymbol: 0,
        });
      },
    },
    message: {
      error: {
        ua: "Це поле обовязкове для заповнення!",
        ru: "Це поле обовязкове для заповнення!",
        eng: "This field is required!",
      },
      check: (value) => {
        return validator.isStrongPassword(value, {
          minLength: 1,
          minLowercase: 0,
          minUppercase: 0,
          minNumbers: 0,
          minSymbols: 0,
          returnScore: false,
          pointsPerUnique: 0,
          pointsPerRepeat: 0,
          pointsForContainingLower: 0,
          pointsForContainingUpper: 0,
          pointsForContainingNumber: 0,
          pointsForContainingSymbol: 0,
        });
      },
    },
    password: {
      error: {
        ua: "Пароль повинен містити більше 6 символів!",
        ru: "Пароль повинен містити більше 6 символів!",
        eng: "Пароль повинен містити більше 6 символів!",
      },
      check: (value) => {
        return validator.isStrongPassword(value, {
          minLength: 6,
          minLowercase: 0,
          minUppercase: 0,
          minNumbers: 0,
          minSymbols: 0,
          returnScore: false,
          pointsPerUnique: 0,
          pointsPerRepeat: 0,
          pointsForContainingLower: 0,
          pointsForContainingUpper: 0,
          pointsForContainingNumber: 0,
          pointsForContainingSymbol: 0,
        });
      },
    },
    password1: {
      error: {
        ua: "Пароль повинен містити більше 6 символів!",
        ru: "Пароль повинен містити більше 6 символів!",
        eng: "Пароль повинен містити більше 6 символів!",
      },
      check: (value) => {
        return validator.isStrongPassword(value, {
          minLength: 6,
          minLowercase: 0,
          minUppercase: 0,
          minNumbers: 0,
          minSymbols: 0,
          returnScore: false,
          pointsPerUnique: 0,
          pointsPerRepeat: 0,
          pointsForContainingLower: 0,
          pointsForContainingUpper: 0,
          pointsForContainingNumber: 0,
          pointsForContainingSymbol: 0,
        });
      },
    },
    password2: {
      error: {
        ua: "Паролі не співпадають!",
        ru: "Паролі не співпадають!",
        eng: "Паролі не співпадають!",
      },
      check: (str) => {
        let comparison = document.querySelector('[data-type="password1"]');
        return validator.equals(str, comparison.value);
      },
    },
  };
  if (validation_btn != null) {
    // обгортка всієї форми
    let wrapper = validation_btn.closest(".validation__block");
    // всі інпути які потрібно провалідувати
    let all_input = wrapper.querySelectorAll(".validation_input");

    // перебір кожного інпута окремо
    all_input.forEach((element) => {
      // обгортка для інпута
      let container = element.closest(".validation_container");
      // пошук в дата атрибуті типу інпуту
      let type = element.dataset.type;
      // додаткова перевірка, на всяк випадок якщо є необхідність
      // динамічно міняти валідацію конкретного інпута
      let required = element.dataset.required;
      // дані які ввів користувач в інпут
      let value = element.value;

      // якщо перевірка по типу спрацювала то все ок,
      // в іншому випадку до змінної з помилкою додається 1

      if (
        (input_type[type].check(`${value}`) && value.length >= 1) ||
        required == "false"
      ) {
        remove_error(container);
        validation_btn.removeAttribute("disabled");
      } else {
        count_error += 1;

        create_error(container, input_type[type].error.ua);
        validation_btn.setAttribute("disabled", "");
      }

      if (element.dataset.event != "active") {
        element.addEventListener("input", function (e) {
          let change_value = e.target.value;
          element.dataset.event = "active";

          if (
            (input_type[type].check(`${change_value}`) &&
              change_value.length >= 1) ||
            required == "false"
          ) {
            let error = container.querySelector(".validation_error");
            if (error != null) {
              count_error -= 1;

              remove_error(container);
              validation_btn.removeAttribute("disabled");
            }
          } else {
            count_error += 1;

            create_error(container, input_type[type].error.ua);
            validation_btn.setAttribute("disabled", "");
          }

          // checkFormErrors(container, validation_btn);
        });
      }
    });
  }

  // якщо помилок не було, до кнопки додається дата атрибут true
  console.log(count_error);

  if (count_error == 0) {
    return true;
  } else {
    return false;
  }

  // створює блок з помилкою
  function create_error(container, text) {
    let check = container.querySelector(".validation_error");
    if (check == null) {
      let error = document.createElement("div");
      error.className = "validation_error";
      error.textContent = text;
      container.append(error);
    }
  }

  // видаляє блок з помилкою
  function remove_error(container) {
    let check = container.querySelector(".validation_error");
    if (check != null) {
      container.querySelector(".validation_error").remove();
    }
  }
}

// export const validationBtn = (formClassName) => {
//   const form = document.querySelector(formClassName);

//   if (form) {
//     const allFields = form.querySelectorAll(".validation_input");
//     const btn = form.querySelector(".validation_btn");

//     if (btn) {
//       btn.addEventListener("click", () => validation(btn));
//     }

//     allFields.forEach((item) =>
//       item.addEventListener("input", () => validation(btn))
//     );

//     allFields.forEach((item) =>
//       item.addEventListener("blur", () => validation(btn))
//     );
//   }
// };

// При валідаційні помилці, будь якого поля, додає для кнопки форми стан disabled

// export function checkFormErrors(form, btn) {
//   const allValidationError = form.querySelectorAll(".validation_error");
//   const isError = allValidationError.length;

//   if (isError) {
//     btn.setAttribute("disabled", "");
//   } else {
//     btn.removeAttribute("disabled");
//   }
// }

// export const validationBtn = (formClassName) => {
//   const form = document.querySelector(formClassName);

//   if (form) {
//     const allFields = form.querySelectorAll(".validation_input");
//     const btn = form.querySelector(".validation_btn");

//     if (btn) {
//       btn.addEventListener("click", () => checkFormErrors(form, btn));
//     }

//     allFields.forEach((item) =>
//       item.addEventListener("input", () => checkFormErrors(form, btn))
//     );

//     allFields.forEach((item) =>
//       item.addEventListener("blur", () => checkFormErrors(form, btn))
//     );
//   }
// };
