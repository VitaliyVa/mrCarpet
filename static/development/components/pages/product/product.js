import { addToBasket } from "../../../api/basket";
import { addToFavorite, removeFromFavorite } from "../../../api/favorites";
import { minus, plus } from "../../module/shop_scripts/basket_action";
import { instance } from "../../../api/instance";

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

    const basketProduct = await addToBasket({
      product: productId,
      quantity: Number(counterValue) || 1,
    });

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
