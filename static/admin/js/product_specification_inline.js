(function($) {
    'use strict';
    
    // Функція для оновлення значень характеристики через AJAX
    function updateSpecValues(specSelect, valueSelect) {
        const selectedSpecId = specSelect.val();
        
        // Зберігаємо вибране значення
        const currentValue = valueSelect.val();
        
        if (!selectedSpecId) {
            // Якщо характеристика не вибрана - очищаємо вибір
            valueSelect.val('');
            return;
        }
        
        // Робимо AJAX запит для отримання значень
        $.ajax({
            url: '/admin/catalog/product/get-spec-values/',
            method: 'GET',
            data: {
                'specification_id': selectedSpecId
            },
            success: function(response) {
                if (response.success && response.values) {
                    // Очищаємо всі опції, але зберігаємо першу (порожню) якщо вона є
                    const firstOption = valueSelect.find('option:first');
                    valueSelect.empty();
                    
                    // Додаємо порожню опцію якщо вона була
                    if (firstOption.length && !firstOption.val()) {
                        valueSelect.append(firstOption.clone());
                    } else {
                        // Якщо немає порожньої опції - додаємо стандартну
                        valueSelect.append($('<option>', { value: '', text: '---------' }));
                    }
                    
                    // Додаємо нові опції
                    $.each(response.values, function(index, value) {
                        const option = $('<option>', {
                            value: value.id,
                            text: value.title || ''
                        });
                        
                        // Якщо це було вибране значення - вибираємо його знову
                        if (currentValue && String(value.id) === String(currentValue)) {
                            option.prop('selected', true);
                        }
                        
                        valueSelect.append(option);
                    });
                }
            },
            error: function(xhr, status, error) {
                // Обробка помилок
            }
        });
    }
    
    // Функція для ініціалізації фільтрації в рядку
    function initSpecFilter(row) {
        // Django admin TabularInline використовує формат імен: productspecification_set-0-specification, productspecification_set-0-spec_value
        // Знаходимо поля specification та spec_value
        // Спробуємо різні варіанти селекторів
        let specSelect = row.find('select[name*="specification"]').not('select[name*="spec_value"]');
        let valueSelect = row.find('select[name*="spec_value"]');
        
        // Якщо не знайдено, пробуємо знайти по класу або іншим способом
        if (!specSelect.length || !valueSelect.length) {
            // Шукаємо всі select в рядку і фільтруємо
            const allSelects = row.find('select');
            if (allSelects.length >= 2) {
                // Перший select зазвичай це specification, другий - spec_value
                specSelect = allSelects.eq(0);
                valueSelect = allSelects.eq(1);
            }
        }
        
        if (!specSelect.length || !valueSelect.length) {
            return;
        }
        
        // Видаляємо старі обробники і додаємо новий
        specSelect.off('change.specFilter');
        
        // Додаємо слухач на зміну specification
        specSelect.on('change.specFilter', function() {
            // Перезначаємо селектори бо можливо змінився контекст
            const currentRow = $(this).closest('.dynamic-productspecification_set, tr');
            const currentSpecSelect = currentRow.find('select[name*="specification"]').not('select[name*="spec_value"]').first();
            const currentValueSelect = currentRow.find('select[name*="spec_value"]').first();
            
            if (currentSpecSelect.length && currentValueSelect.length) {
                updateSpecValues(currentSpecSelect, currentValueSelect);
            }
        });
        
        // Ініціалізуємо фільтр для поточного стану (якщо характеристика вже вибрана)
        if (specSelect.val()) {
            updateSpecValues(specSelect, valueSelect);
        }
    }
    
    // Функція для ініціалізації всіх рядків
    function initAllSpecFilters() {
        // Знаходимо всі inline рядки для ProductSpecification
        // Клас форми: dynamic-productspecification_set (для TabularInline)
        // Також пробуємо знайти по tr в inline-group
        let rows = $('.dynamic-productspecification_set');
        
        // Якщо не знайдено по класу, пробуємо знайти по наявності select з specification
        if (!rows.length) {
            rows = $('select[name*="specification"]').not('select[name*="spec_value"]').closest('tr, .form-row');
        }
        
        rows.each(function() {
            initSpecFilter($(this));
        });
    }
    
    // Ініціалізація при завантаженні сторінки
    $(document).ready(function() {
        // Затримка для впевненості що inline форми вже відрендерені
        setTimeout(function() {
            initAllSpecFilters();
        }, 200);
        
        // Додаємо делегування подій на рівні document для обробки змін в динамічно доданих елементах
        $(document).on('change', 'select[name*="specification"]', function(e) {
            // Перевіряємо що це не spec_value
            if ($(this).attr('name') && $(this).attr('name').indexOf('spec_value') !== -1) {
                return;
            }
            
            const $specSelect = $(this);
            const $row = $specSelect.closest('tr, .dynamic-productspecification_set, .form-row');
            const $valueSelect = $row.find('select[name*="spec_value"]').first();
            
            if ($valueSelect.length) {
                updateSpecValues($specSelect, $valueSelect);
            }
        });
        
        // Підтримка додавання нових рядків через formset
        // Django admin використовує CustomEvent 'formset:added' з detail.formsetName
        document.addEventListener('formset:added', function(event) {
            const formsetName = event.detail && event.detail.formsetName;
            if (formsetName && formsetName.startsWith('productspecification_set')) {
                // Знаходимо доданий рядок
                let $row = $(event.target);
                // Якщо event.target не рядок, шукаємо найближчий рядок з класом dynamic-productspecification_set
                if (!$row.hasClass('dynamic-productspecification_set') && !$row.is('tr')) {
                    $row = $row.closest('.dynamic-productspecification_set, tr');
                }
                if ($row.length) {
                    setTimeout(function() {
                        initSpecFilter($row);
                    }, 50);
                }
            }
        });
    });
    
})(django.jQuery || jQuery);
