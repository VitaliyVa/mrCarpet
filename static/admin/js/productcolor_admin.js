(function($) {
    'use strict';
    
    $(document).ready(function() {
        // Створюємо блок для роботи з кольорами
        const productNameField = $('#product_name_search_field');
        if (!productNameField.length) return;
        
        const fieldRow = productNameField.closest('.form-row');
        const colorsBlock = $('<div>', {
            id: 'product-colors-search-block',
            class: 'product-colors-search-block'
        });
        
        // Додаємо кнопку "Оновити кольори"
        const updateButton = $('<button>', {
            type: 'button',
            class: 'button update-colors-btn',
            text: 'Оновити кольори'
        });
        
        // Додаємо блок для відображення результатів
        const resultsBlock = $('<div>', {
            id: 'product-colors-results',
            class: 'product-colors-results'
        });
        
        // Додаємо блок для відображення вибраних кольорів
        const selectedColorsBlock = $('<div>', {
            id: 'selected-colors-list',
            class: 'selected-colors-list'
        });
        
        colorsBlock.append(updateButton);
        colorsBlock.append(resultsBlock);
        colorsBlock.append(selectedColorsBlock);
        
        // Додаємо блок після поля пошуку
        fieldRow.after($('<div>', {class: 'form-row'}).append(colorsBlock));
        
        let selectedColorIds = [];
        
        // Функція для отримання CSRF token
        function getCookie(name) {
            let cookieValue = null;
            if (document.cookie && document.cookie !== '') {
                const cookies = document.cookie.split(';');
                for (let i = 0; i < cookies.length; i++) {
                    const cookie = cookies[i].trim();
                    if (cookie.substring(0, name.length + 1) === (name + '=')) {
                        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                        break;
                    }
                }
            }
            return cookieValue;
        }
        
        // Обробник кнопки "Оновити кольори"
        updateButton.on('click', function() {
            const productName = productNameField.val().trim();
            
            if (!productName) {
                alert('Будь ласка, введіть назву товару');
                return;
            }
            
            updateButton.prop('disabled', true).text('Пошук...');
            resultsBlock.html('');
            selectedColorsBlock.html('');
            selectedColorIds = [];
            
            const csrftoken = getCookie('csrftoken');
            
            // AJAX запит на пошук товарів
            $.ajax({
                url: '/admin/catalog/productcolor/search-products-by-name/',
                method: 'GET',
                headers: {
                    'X-CSRFToken': csrftoken
                },
                data: {
                    product_name: productName
                },
                success: function(response) {
                    if (response.error) {
                        alert('Помилка: ' + response.error);
                        updateButton.prop('disabled', false).text('Оновити кольори');
                        return;
                    }
                    
                    if (response.count === 0) {
                        resultsBlock.html('<p class="no-products">Товари з такою назвою не знайдено</p>');
                        updateButton.prop('disabled', false).text('Оновити кольори');
                        return;
                    }
                    
                    // Відображаємо список товарів з їх активними кольорами
                    const productsList = $('<ul>', {class: 'products-list'});
                    
                    response.products.forEach(function(product) {
                        const productItem = $('<li>', {
                            class: 'product-item',
                            'data-product-id': product.id
                        });
                        
                        const colorInfo = product.active_color_id 
                            ? `<span class="color-preview" style="background-color: ${product.active_color_color};" title="${product.active_color_title}"></span> ${product.active_color_title}`
                            : '<span class="no-color">Колір не вказано</span>';
                        
                        productItem.html(`
                            <div class="product-title">${product.title}</div>
                            <div class="product-color">${colorInfo}</div>
                        `);
                        
                        // Якщо у товару є активний колір, додаємо його до вибраних
                        if (product.active_color_id && selectedColorIds.indexOf(product.active_color_id) === -1) {
                            selectedColorIds.push(product.active_color_id);
                            addColorToList(product.active_color_id, product.active_color_title, product.active_color_color, product.active_color_slug);
                        }
                        
                        productsList.append(productItem);
                    });
                    
                    resultsBlock.html(`<h3>Знайдено товарів: ${response.count}</h3>`).append(productsList);
                    
                    // Автоматично вибираємо всі знайдені кольори в ManyToMany полі
                    if (selectedColorIds.length > 0) {
                        selectColorsInManyToMany(selectedColorIds);
                    }
                    
                    updateButton.prop('disabled', false).text('Оновити кольори');
                },
                error: function(xhr) {
                    let errorMsg = 'Помилка при пошуку товарів';
                    try {
                        const response = JSON.parse(xhr.responseText);
                        if (response.error) {
                            errorMsg = response.error;
                        }
                    } catch(e) {
                        errorMsg = 'Помилка сервера';
                    }
                    alert('Помилка: ' + errorMsg);
                    updateButton.prop('disabled', false).text('Оновити кольори');
                }
            });
        });
        
        // Функція для додавання кольору до списку вибраних
        function addColorToList(colorId, colorTitle, colorValue, colorSlug) {
            const colorItem = $('<div>', {
                class: 'selected-color-item',
                'data-color-id': colorId
            });
            
            colorItem.html(`
                <span class="color-preview" style="background-color: ${colorValue};" title="${colorTitle}"></span>
                <span class="color-title">${colorTitle}</span>
                <button type="button" class="remove-color-btn" data-color-id="${colorId}">×</button>
            `);
            
            // Обробник видалення кольору
            colorItem.find('.remove-color-btn').on('click', function() {
                const id = parseInt($(this).data('color-id'));
                selectedColorIds = selectedColorIds.filter(cid => cid !== id);
                colorItem.remove();
                selectColorsInManyToMany(selectedColorIds);
            });
            
            selectedColorsBlock.append(colorItem);
            
            // Показуємо блок якщо є кольори
            if (selectedColorsBlock.children().length > 0) {
                selectedColorsBlock.show();
            }
        }
        
        // Функція для автоматичного вибору кольорів в ManyToMany полі
        function selectColorsInManyToMany(colorIds) {
            if (!colorIds || colorIds.length === 0) return;
            
            // Django admin використовує FilteredSelectMultiple для ManyToMany полів
            // Перевіряємо чи є FilteredSelectMultiple (два select: from та to)
            const fromSelect = $('#id_colors_from');
            const toSelect = $('#id_colors_to');
            
            if (fromSelect.length && toSelect.length) {
                // FilteredSelectMultiple - два select (from та to)
                // Використовуємо стандартний механізм Django admin SelectBox
                const fromSelectId = fromSelect.attr('id');
                const toSelectId = toSelect.attr('id');
                
                // Спочатку вибираємо всі потрібні опції в "from"
                let hasNewSelections = false;
                colorIds.forEach(function(colorId) {
                    // Перевіряємо чи вже вибрано в "to"
                    const alreadySelected = toSelect.find(`option[value="${colorId}"]`).length > 0;
                    
                    if (!alreadySelected) {
                        // Знаходимо опцію в "from"
                        const option = fromSelect.find(`option[value="${colorId}"]`);
                        if (option.length > 0) {
                            // Вибираємо опцію в from select
                            option.prop('selected', true);
                            hasNewSelections = true;
                        }
                    }
                });
                
                // Якщо є нові вибрані опції, переміщуємо їх одним викликом
                if (hasNewSelections) {
                    if (typeof SelectBox !== 'undefined') {
                        try {
                            // Ініціалізуємо SelectBox для обох select якщо потрібно
                            if (!SelectBox.cache[fromSelectId]) {
                                SelectBox.init(fromSelectId);
                            }
                            if (!SelectBox.cache[toSelectId]) {
                                SelectBox.init(toSelectId);
                            }
                            
                            // Використовуємо SelectBox.move для переміщення вибраних опцій
                            SelectBox.move(fromSelectId, toSelectId);
                            
                            // Оновлюємо відображення обох select
                            SelectBox.redisplay(fromSelectId);
                            SelectBox.redisplay(toSelectId);
                        } catch(e) {
                            console.log('Помилка при переміщенні кольорів:', e);
                            // Альтернативний спосіб - через кнопку додавання
                            const addLink = fromSelect.closest('.selector').find('a.selector-chooseall, a[id*="add"]');
                            if (addLink.length) {
                                setTimeout(function() {
                                    addLink.first().click();
                                }, 50);
                            }
                        }
                    } else {
                        // Альтернативний спосіб - через кнопку додавання
                        const addLink = fromSelect.closest('.selector').find('a.selector-chooseall, a[id*="add"]');
                        if (addLink.length) {
                            setTimeout(function() {
                                addLink.first().click();
                            }, 50);
                        }
                    }
                }
            } else {
                // Звичайний select multiple (не FilteredSelectMultiple)
                const selectBox = $('#id_colors');
                if (selectBox.length) {
                    colorIds.forEach(function(colorId) {
                        const option = selectBox.find(`option[value="${colorId}"]`);
                        if (option.length) {
                            option.prop('selected', true);
                        }
                    });
                    selectBox.trigger('change');
                }
            }
        }
        
        // Дозволяємо пошук по Enter
        productNameField.on('keypress', function(e) {
            if (e.which === 13) {
                e.preventDefault();
                updateButton.trigger('click');
            }
        });
    });
})(django.jQuery || jQuery);
