function minus(itemClassName, input_name, target) {
  let item = target.closest(itemClassName);
  let input = item.querySelector(input_name);
  let value = Number(input.value);

  if (value <= 1) {
    input.value = 1;
  } else {
    input.value = value - 1;
  }

  return Number(input.value);
}

function plus(itemClassName, input_name, target) {
  let item = target.closest(itemClassName);
  let input = item.querySelector(input_name);
  let value = Number(input.value);

  input.value = value + 1;

  return Number(input.value);
}

function input_basket(input_name) {
  let input = input_name;
  let value = Number(input.value);

  if (value <= 0) {
    input.value = 1;
  }

  return Number(input.value);
}

function delete_item(target, itemClassName) {
  let item = target.closest(itemClassName);

  item.style.position = "relative";
  item.style.transition = "all .2s";
  item.style.maxHeight = "1000px";
  item.style.opacity = "0";

  item.style.transform = "scale(0)";
  setTimeout(() => {
    item.style.position = "absolute";
  }, 200);
  setTimeout(() => {
    item.remove();
  }, 1000);
}

export { minus, plus, input_basket, delete_item };
