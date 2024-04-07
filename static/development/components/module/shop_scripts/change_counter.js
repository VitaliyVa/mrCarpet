function change_counter(val, up, className) {
  let old_count = Number(document.querySelector(className).textContent);
  let result;
  document.querySelector(className).style.transform = "scale(1.3)";
  setTimeout(() => {
    document.querySelector(className).style.transform = "scale(1)";
  }, 200);

  if (up == true) {
    result = old_count + val;
  } else if (up == false) {
    result = old_count - val;
  } else if (up == null) {
    result = val;
  }
  document.querySelector(className).textContent = result;
}

export { change_counter };
