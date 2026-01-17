import { addToBasket } from "../../../api/basket";
import { addToFavorite, removeFromFavorite } from "../../../api/favorites";
import { minus, plus } from "../../module/shop_scripts/basket_action";
import { instance } from "../../../api/instance";
import Choices from "choices.js";
import { showError } from "../../../utils/notifications";

// Логіка для кастомних товарів
function initCustomProductLogic() {
  const customSizeBlocks = document.querySelectorAll('.custom-size-block');
  
  customSizeBlocks.forEach((block) => {
    const widthSelectElement = block.querySelector('.custom-size-width-select');
    const lengthInput = block.querySelector('.custom-size-length-input');
    const errorSpan = block.querySelector('.custom-size-error');
    
    // Обгортаємо інпут довжини в обгортку для відображення "м."
    if (lengthInput && !lengthInput.parentElement.classList.contains('custom-size-length-wrapper')) {
      const wrapper = document.createElement('div');
      wrapper.className = 'custom-size-length-wrapper';
      lengthInput.parentNode.insertBefore(wrapper, lengthInput);
      wrapper.appendChild(lengthInput);
    }
    const minLen = parseFloat(block.dataset.minLen);
    const maxLen = parseFloat(block.dataset.maxLen);
    const customPrice = parseFloat(block.dataset.customPrice);
    const product = block.closest('.product');
    const priceElement = product?.querySelector('.cart_item_price-value');
    const priceBlock = product?.querySelector('.cart_item_price__block');
    
    // Створюємо елемент для відображення повної ціни (коли вибрана довжина)
    let totalPriceElement = null;
    if (priceBlock) {
      totalPriceElement = document.createElement('p');
      totalPriceElement.className = 'cart_item_price medium color_gold custom-total-price';
      totalPriceElement.style.display = 'none';
      totalPriceElement.style.marginTop = '8px';
      totalPriceElement.style.width = '100%';
      priceBlock.style.display = 'flex';
      priceBlock.style.flexDirection = 'column';
      priceBlock.appendChild(totalPriceElement);
    }
    
    // Функція валідації довжини
    function validateLength(value) {
      const numValue = parseFloat(value);
      
      if (!value || isNaN(numValue)) {
        errorSpan.textContent = '';
        errorSpan.classList.remove('show');
        lengthInput.classList.remove('error');
        return false;
      }
      
      if (numValue < minLen) {
        errorSpan.textContent = `Мінімальна довжина: ${minLen}м`;
        errorSpan.classList.add('show');
        lengthInput.classList.add('error');
        return false;
      }
      
      if (numValue > maxLen) {
        errorSpan.textContent = `Максимальна довжина: ${maxLen}м`;
        errorSpan.classList.add('show');
        lengthInput.classList.add('error');
        return false;
      }
      
      errorSpan.textContent = '';
      errorSpan.classList.remove('show');
      lengthInput.classList.remove('error');
      return true;
    }
    
    // Ініціалізація Choices.js для селекта ширини
    let widthChoices = null;
    if (widthSelectElement) {
      widthChoices = new Choices(widthSelectElement, {
        searchEnabled: false,
        itemSelectText: "",
        shouldSort: false,
        removeItemButton: false,
        placeholderValue: "Оберіть ширину",
      });
    }
    
    // Функція обчислення та оновлення ціни
    function calculatePrice() {
      const widthValue = widthSelectElement?.value || '';
      const width = parseFloat(widthValue);
      const length = parseFloat(lengthInput.value);
      
      // Приховуємо блок повної ціни, якщо немає ширини або довжини
      if (!width || !length || isNaN(width) || isNaN(length)) {
        if (totalPriceElement) {
          totalPriceElement.style.display = 'none';
        }
        return;
      }
      
      if (!validateLength(length)) {
        if (totalPriceElement) {
          totalPriceElement.style.display = 'none';
        }
        return;
      }
      
      const totalPrice = customPrice * width * length;
      const formattedPrice = totalPrice % 1 === 0 
        ? totalPrice.toFixed(0) 
        : totalPrice.toFixed(2);
      
      // Показуємо повну ціну нижче на новому рядку
      if (totalPriceElement) {
        totalPriceElement.innerHTML = `<span class="cart_item_price-value">${formattedPrice}</span> <span>грн</span>`;
        totalPriceElement.style.display = 'block';
      }
    }
    
    // Обробник подій для селекта ширини
    if (widthSelectElement) {
      widthSelectElement.addEventListener('change', calculatePrice);
    }
    lengthInput.addEventListener('input', function() {
      validateLength(this.value);
      calculatePrice();
    });
    lengthInput.addEventListener('blur', function() {
      validateLength(this.value);
      calculatePrice(); // Оновлюємо відображення "/м²" при втраті фокусу
    });
  });
}

// Ініціалізація при завантаженні сторінки
document.addEventListener('DOMContentLoaded', initCustomProductLogic);

document.addEventListener("click", async ({ target }) => {
  const product = target.closest(".product");
  const productId = product?.dataset?.productId;

  const addToBasketButton = target.closest(".add-to-cart");
  const addToFavoriteButton = target.closest(".product_favourite-btn");
  const characteristicValue = target.closest(".characteristic-value");
  const colorLabel = target.closest(".color-label");

  const counterMinusButton = target.closest(".counter__minus-btn");
  const counterPlusButton = target.closest(".counter__plus-btn");

  // click on color label - redirect to product with this active_color
  if (colorLabel) {
    const colorId = colorLabel.dataset.colorId;
    const productTitle = colorLabel.dataset.productTitle;
    
    if (colorId && productTitle) {
      console.log('Пошук товару:', { productTitle, colorId });
      
      // Шукаємо товар з однаковим title та active_color = обраному кольору
      // Використовуємо API для пошуку товару
      try {
        // Використовуємо page_size для отримання більшої кількості результатів
        // Це важливо якщо товарів багато і є пагінація
        const searchUrl = `/products/?search_query=${encodeURIComponent(productTitle)}&page_size=100`;
        console.log('API запит:', searchUrl);
        
        const response = await instance.get(searchUrl);
        const data = response.data;
        
        console.log('API відповідь:', data);
        
        if (data && data.results) {
          console.log('Знайдено товарів:', data.results.length);
          console.log('Всі знайдені товари:', data.results.map(p => ({ title: p.title, colorId: p.active_color?.id })));
          
          // Знаходимо товар з ТОЧНИМ title та active_color = обраному кольору
          const targetProduct = data.results.find(p => {
            const titleMatch = p.title && p.title.toLowerCase() === productTitle.toLowerCase();
            const colorMatch = p.active_color && parseInt(p.active_color.id) === parseInt(colorId);
            
            console.log('Перевірка товару:', {
              title: p.title,
              titleMatch,
              activeColorId: p.active_color?.id,
              colorMatch,
              expectedColorId: colorId
            });
            
            return titleMatch && colorMatch;
          });
          
          if (targetProduct && targetProduct.slug) {
            console.log('Знайдено товар для редиректу:', targetProduct.slug);
            // Перекидаємо на товар з цим active_color
            window.location.href = `/catalog/product/${targetProduct.slug}/`;
            return;
          } else {
            console.warn('Товар не знайдено. Шукали:', { productTitle, colorId });
            // Якщо не знайдено товар з точним title та colorId, спробуємо знайти хоча б по title
            const fallbackProduct = data.results.find(p => 
              p.title && p.title.toLowerCase() === productTitle.toLowerCase()
            );
            
            if (fallbackProduct && fallbackProduct.slug) {
              console.log('Знайдено товар без перевірки кольору:', fallbackProduct.slug);
              window.location.href = `/catalog/product/${fallbackProduct.slug}/`;
              return;
            }
          }
        }
      } catch (error) {
        console.error('Помилка при пошуку товару:', error);
        // Якщо пошук не вдався, просто перемикаємо активний колір
      }
    }
    
    // Якщо товар не знайдено, просто перемикаємо активний колір
    const colorsBlock = colorLabel.closest(".colors-block");
    if (colorsBlock) {
      const allColorLabels = colorsBlock.querySelectorAll(".color-label");
      allColorLabels.forEach((label) => {
        label.classList.remove("active");
      });
      colorLabel.classList.add("active");
    }
    return;
  }

  // click on characteristic value - redirect to catalog with filter
  if (characteristicValue) {
    const specName = characteristicValue.dataset.specName;
    const specValue = characteristicValue.dataset.specValue;
    const categorySlug = characteristicValue.dataset.categorySlug;

    if (specName && specValue && categorySlug) {
      // Перетворюємо назву специфікації в нижній регістр для URL
      const specNameLower = specName.toLowerCase();
      
      // Кодуємо значення для URL
      const encodedSpecValue = encodeURIComponent(specValue);
      
      // Будуємо URL: /catalog/categorie/{category_slug}/?{spec_name_lower}={spec_value}
      const catalogUrl = `/catalog/categorie/${categorySlug}/?${specNameLower}=${encodedSpecValue}`;
      
      // Перенаправляємо на каталог з фільтром
      window.location.href = catalogUrl;
      return;
    }
  }

  // add to basket
  if (addToBasketButton) {
    const counterValue = product.querySelector(".counter__value").value;
    const customSizeBlock = product.querySelector(".custom-size-block");
    
    const basketData = {
      product: productId,
      quantity: Number(counterValue) || 1,
    };
    
    // Якщо це кастомний товар, перевіряємо та додаємо width та length
    if (customSizeBlock) {
      const widthSelectElement = customSizeBlock.querySelector(".custom-size-width-select");
      const lengthInput = customSizeBlock.querySelector(".custom-size-length-input");
      
      // Отримуємо значення з select (Choices автоматично синхронізує з оригінальним select)
      const selectedWidthValue = widthSelectElement?.value;
      const lengthValue = lengthInput?.value;
      
      // Валідація для кастомного товару
      if (!selectedWidthValue || !lengthValue) {
        showError("Будь ласка, виберіть ширину та введіть довжину для кастомного килима");
        return;
      }
      
      // Перевіряємо валідність довжини (перевірка вже в initCustomProductLogic, але перевіримо ще раз)
      const minLen = parseFloat(customSizeBlock.dataset.minLen);
      const maxLen = parseFloat(customSizeBlock.dataset.maxLen);
      const lengthNum = parseFloat(lengthValue);
      
      if (isNaN(lengthNum) || lengthNum < minLen || lengthNum > maxLen) {
        showError(`Довжина повинна бути від ${minLen}м до ${maxLen}м`);
        return;
      }
      
      // Отримуємо ID ProductWidth з обраної опції
      const selectedOption = widthSelectElement?.querySelector(`option[value="${selectedWidthValue}"]`);
      const widthId = selectedOption?.dataset?.widthId;
      
      if (widthId && lengthValue) {
        basketData.width = parseInt(widthId);
        basketData.length = parseFloat(lengthValue);
      }
    }

    const basketProduct = await addToBasket(basketData);

    console.log(basketProduct);
  }

  // add to favourite
  if (addToFavoriteButton) {
    const isAdded = addToFavoriteButton.classList.contains("active");

    if (!isAdded) {
      await addToFavorite(productId, () =>
        addToFavoriteButton.classList.add("active")
      );
    } else {
      await removeFromFavorite(productId, () =>
        addToFavoriteButton.classList.remove("active")
      );
    }
  }

  if (counterMinusButton) {
    minus(".counter", ".counter__value", target);
  }

  if (counterPlusButton) {
    plus(".counter", ".counter__value", target);
  }
});
