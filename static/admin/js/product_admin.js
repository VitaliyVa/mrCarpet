(function($) {
    'use strict';
    
    $(document).ready(function() {
        // Знаходимо поле active_color
        const activeColorField = $('#id_active_color');
        if (!activeColorField.length) return;
        
        // Знаходимо рядок з полем active_color
        const activeColorRow = activeColorField.closest('.form-row');
        if (!activeColorRow.length) return;
        
        // Створюємо блок для кнопки "Оновити кольори"
        const updateColorsBlock = $('<div>', {
            id: 'product-update-colors-block',
            class: 'product-update-colors-block'
        });
        
        // Додаємо кнопку "Оновити кольори"
        const updateButton = $('<button>', {
            type: 'button',
            class: 'button update-colors-btn',
            text: 'Оновити кольори'
        });
        
        // Додаємо блок для відображення результатів
        const resultsBlock = $('<div>', {
            id: 'update-colors-results',
            class: 'update-colors-results'
        });
        
        updateColorsBlock.append(updateButton);
        updateColorsBlock.append(resultsBlock);
        
        // Додаємо блок після поля active_color
        activeColorRow.after($('<div>', {class: 'form-row'}).append(updateColorsBlock));
        
        // Отримуємо object_id з URL або з форми
        function getObjectId() {
            // Спробуємо отримати з URL
            const urlPath = window.location.pathname;
            
            // Перевіряємо чи це сторінка додавання
            if (urlPath.includes('/add/') || urlPath.endsWith('/add')) {
                return null;
            }
            
            // Шукаємо pattern: /change/{id}/ або /change/{id}
            const changeMatch = urlPath.match(/\/change\/(\d+)\/?$/);
            if (changeMatch && changeMatch[1]) {
                return changeMatch[1];
            }
            
            // Альтернативний спосіб: шукаємо в URL pattern: /product/{id}/change/
            const productChangeMatch = urlPath.match(/\/product\/(\d+)\/change/);
            if (productChangeMatch && productChangeMatch[1]) {
                return productChangeMatch[1];
            }
            
            // Спробуємо отримати з форми (action attribute)
            const form = $('form[action*="change"]');
            if (form.length) {
                const actionUrl = form.attr('action');
                if (actionUrl) {
                    const actionMatch = actionUrl.match(/\/(\d+)\/change\//);
                    if (actionMatch && actionMatch[1]) {
                        return actionMatch[1];
                    }
                }
            }
            
            // Спробуємо отримати з поля id (якщо існує)
            const idField = $('#id');
            if (idField.length && idField.val()) {
                return idField.val();
            }
            
            // Останній варіант: парсимо URL по частинах
            const urlParts = urlPath.split('/').filter(function(part) {
                return part !== '' && part !== 'change';
            });
            
            // Шукаємо число в URL (це має бути object_id)
            for (let i = urlParts.length - 1; i >= 0; i--) {
                const part = urlParts[i];
                if (/^\d+$/.test(part)) {
                    return part;
                }
            }
            
            return null;
        }
        
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
            const urlPath = window.location.pathname;
            const isAddPage = urlPath.includes('/add/') || urlPath.endsWith('/add');
            
            // Якщо це сторінка додавання, не дозволяємо оновлення
            if (isAddPage) {
                alert('Спочатку збережіть товар, щоб оновити кольори');
                return;
            }
            
            const objectId = getObjectId();
            
            // Перевіряємо чи вдалося отримати object_id
            if (!objectId) {
                console.error('Не вдалося отримати object_id. URL:', urlPath);
                alert('Помилка: не вдалося визначити ID товару. Перезавантажте сторінку та спробуйте ще раз.');
                return;
            }
            
            // Перевіряємо чи object_id - це число
            if (!/^\d+$/.test(objectId)) {
                console.error('Невірний формат object_id:', objectId);
                alert('Помилка: не вдалося визначити ID товару. Перезавантажте сторінку та спробуйте ще раз.');
                return;
            }
            
            console.log('Object ID знайдено:', objectId);
            
            const titleField = $('#id_title');
            const productTitle = titleField.val().trim();
            
            if (!productTitle) {
                alert('Будь ласка, введіть назву товару');
                return;
            }
            
            updateButton.prop('disabled', true).text('Оновлення...');
            resultsBlock.html('');
            
            const csrftoken = getCookie('csrftoken');
            
            // AJAX запит на оновлення кольорів
            $.ajax({
                url: `/admin/catalog/product/${objectId}/update-colors-from-title/`,
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrftoken
                },
                success: function(response) {
                    if (response.error) {
                        alert('Помилка: ' + response.error);
                        updateButton.prop('disabled', false).text('Оновити кольори');
                        return;
                    }
                    
                    // Показуємо результат
                    resultsBlock.html(`
                        <div class="update-colors-success">
                            <strong>Успішно!</strong> ${response.message}
                            ${response.colors_count > 0 ? `<br>Додано кольорів: ${response.colors_count}` : ''}
                        </div>
                    `);
                    
                    // Автоматично вибираємо всі знайдені кольори в ManyToMany полі
                    if (response.colors && response.colors.length > 0) {
                        const colorIds = response.colors.map(c => c.id);
                        selectColorsInManyToMany(colorIds);
                    }
                    
                    updateButton.prop('disabled', false).text('Оновити кольори');
                },
                error: function(xhr) {
                    let errorMsg = 'Помилка при оновленні кольорів';
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
        
        // Функція для автоматичного вибору кольорів в ManyToMany полі
        function selectColorsInManyToMany(colorIds) {
            if (!colorIds || colorIds.length === 0) return;
            
            // Django admin використовує FilteredSelectMultiple для ManyToMany полів
            // Перевіряємо чи є FilteredSelectMultiple (два select: from та to)
            const fromSelect = $('#id_colors_from');
            const toSelect = $('#id_colors_to');
            
            if (fromSelect.length && toSelect.length) {
                // FilteredSelectMultiple - два select (from та to)
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
    });
})(django.jQuery || jQuery);
