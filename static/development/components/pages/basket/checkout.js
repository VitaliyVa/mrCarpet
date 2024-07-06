import {
  createOrder,
  getSettlements,
  getWarehouses,
} from "../../../api/checkout";
import { bad_modal, getFormFields } from "../../module/form_action";
import validation from "../../module/validation";

const checkboxItems = document.querySelectorAll(".basket__checkbox-item");

document.addEventListener("click", (event) => {
  event.preventDefault();

  const accordionTitle = event.target.closest(".accordion__title");
  const bodyBlockEditBtn = event.target.closest(
    ".basket__checkbox-item-body-block-edit-btn"
  );

  // Control accordion and checkboxes
  if (accordionTitle) {
    const accordionContentBlock = accordionTitle.closest(
      ".accordion_content__block"
    );
    const checkboxInput =
      accordionContentBlock.querySelector(".checkbox__input");

    checkboxInput.checked = true;
    accordionContentBlock.classList.add("active");

    checkboxItems.forEach((item) => {
      if (!item.querySelector(".checkbox__input").checked) {
        item.classList.remove("active");
      }
    });
  }

  // Unlocking editing of address and contact data fields
  if (bodyBlockEditBtn) {
    const bodyBlock = bodyBlockEditBtn.closest(
      ".basket__checkbox-item-body-block"
    );
    const bodyBlockFields = bodyBlock.querySelectorAll("input");

    if (bodyBlockEditBtn.classList.contains("active")) {
      bodyBlockEditBtn.classList.remove("active");
      bodyBlockFields.forEach((item) => (item.readOnly = true));
    } else {
      bodyBlockEditBtn.classList.add("active");
      bodyBlockFields.forEach((item) => (item.readOnly = false));
    }
  }

  // send order

  let activeDeliveryElement = null;
  let activePaymentElement = null;

  checkboxItems.forEach((item) => {
    if (item.querySelector(".checkbox__input").checked) {
      if (item.closest(".basket__delivery-item")) {
        activeDeliveryElement = item;
      }

      if (item.closest(".basket__payment-item")) {
        activePaymentElement = item;
      }
    }
  });

  const formValues = {
    name: activeDeliveryElement.querySelector("[id='name']").value,
    // surname: "",
    // email: activeDeliveryElement.querySelector("[id='email']").value,
    phone: activeDeliveryElement.querySelector("[id='phone']").value,
    address: "",
    payment_type: activePaymentElement.querySelector(".checkbox__input").id,
  };

  console.log(formValues);

  const submitOrderButton = event.target.closest(".basket__to-order-btn");

  if (submitOrderButton) {
    createOrder(formValues);
  }
});

// render select items, отримання міст та відділень та їх додаванно до списку
const renderSelectItem = ({ id, title }) => {
  return `<li id=${id} class="custom-select__list-item">${title}</li>`;
};

export const renderSelectItems = (items, classNameSelect) => {
  const select = document.querySelector(classNameSelect);
  const selectList = select.querySelector(".custom-select__list");
  const newSelectItems = items?.map((item) => renderSelectItem(item));

  if (newSelectItems) {
    selectList.innerHTML = newSelectItems.join("");
  } else {
    selectList.innerHTML = "";
  }
};

const selectSettlement = document.querySelector(".select-settlement");
const selectWarehouse = document.querySelector(".select-warehouse");
const selectSettlementInput = selectSettlement.querySelector("input");
const selectWarehouseInput = selectWarehouse.querySelector("input");

selectSettlementInput.addEventListener("input", async ({ target }) => {
  if (target.value.length) {
    const data = await getSettlements(target.value);

    console.log("test");

    renderSelectItems(data?.results, ".select-settlement");
  }

  selectWarehouse.querySelector(".custom-select__list").innerHTML = "";
});

selectSettlement.addEventListener("click", async ({ target }) => {
  if (target.closest(".custom-select__list-item")) {
    const data = await getWarehouses(target.id);

    renderSelectItems(data, ".select-warehouse");
  }
});

selectWarehouseInput.addEventListener("input", async ({ target }) => {
  const resetExtraSymbols = (str) => {
    return str
      .toLocaleLowerCase()
      .replaceAll("нова пошта", "")
      .replaceAll("вулиця", "")
      .replaceAll("вул", "")
      .replaceAll("№", "")
      .replaceAll('"', "")
      .replaceAll(":", "")
      .replaceAll("(", "")
      .replaceAll(")", "")
      .replaceAll(".", "")
      .replaceAll(",", "")
      .replaceAll(" ", "");
  };

  const searchValue = resetExtraSymbols(target.value);

  const warehouses = await getWarehouses(
    selectSettlementInput.dataset.listItemId
  );

  const filteredWarehouses = warehouses?.filter((item) => {
    const itemTitle = resetExtraSymbols(item.title);

    return itemTitle.includes(searchValue);
  });

  renderSelectItems(filteredWarehouses, ".select-warehouse");
});
