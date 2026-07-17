/**
 * Client-side validation for Product admin before POST.
 * Mirrors catalog.admin_forms (ProductAdminForm / ProductAttributeAdminForm).
 */
(function () {
    'use strict';

    var MSG = {
        required: "Це поле обов'язкове.",
        needAttr: 'Додайте хоча б одну варіацію (розмір + ціна + кількість).',
        needCategory: 'Оберіть хоча б одну категорію.',
        needImage: 'Завантажте каталожне зображення.',
        bannerOne: 'Заповніть обовʼязкове поле нижче — збереження скасовано.',
        bannerMany: function (n) {
            return 'Заповніть обовʼязкові поля (' + n + ') — збереження скасовано.';
        },
    };

    var CLS = {
        field: 'client-field-invalid',
        row: 'client-row-invalid',
        msg: 'client-field-error-msg',
        banner: 'client-validation-banner',
    };

    var DEFAULT_IMAGE = 'products/default.png';

    function ready(fn) {
        if (document.readyState !== 'loading') fn();
        else document.addEventListener('DOMContentLoaded', fn);
    }

    function controlHasValue(el) {
        if (!el || el.disabled) return false;
        if (el.type === 'checkbox' || el.type === 'radio') return el.checked;
        if (el.type === 'file') return !!(el.files && el.files.length);
        if (el.tagName === 'SELECT') {
            if (el.multiple) {
                return Array.prototype.some.call(el.selectedOptions || [], function (o) {
                    return !!o.value;
                });
            }
            return String(el.value || '').trim() !== '';
        }
        return String(el.value || '').trim() !== '';
    }

    function rowIsDeleted(row) {
        var del = row.querySelector('input[type="checkbox"][name$="-DELETE"]');
        return !!(del && del.checked);
    }

    function isSkippableControl(el) {
        if (!el.name) return true;
        if (el.type === 'hidden') return true;
        if (/-(id|DELETE)$/.test(el.name)) return true;
        // parent FK on inlines
        if (/-(product|related_to)$/.test(el.name) && el.type === 'hidden') return true;
        return false;
    }

    function rowHasUserInput(row) {
        var controls = row.querySelectorAll('input, select, textarea');
        for (var i = 0; i < controls.length; i++) {
            var el = controls[i];
            if (isSkippableControl(el)) continue;
            if ((el.type === 'checkbox' || el.type === 'radio') && !el.checked) continue;
            if (controlHasValue(el)) return true;
        }
        return false;
    }

    function eachInlineRow(form, groupId, fn) {
        var group = form.querySelector('#' + groupId);
        if (!group) return;
        group.querySelectorAll('tr.form-row, div.form-row').forEach(function (row) {
            if (row.classList.contains('empty-form')) return;
            if (rowIsDeleted(row)) return;
            if (!rowHasUserInput(row)) return;
            fn(row);
        });
    }

    function findField(row, suffix) {
        return row.querySelector('[name$="-' + suffix + '"]');
    }

    /** True if widget shows a current non-default file link and clear is unchecked. */
    function hasExistingFile(root, fieldSuffix) {
        if (!root) return false;
        var clear =
            root.querySelector('input[type="checkbox"][name$="-' + fieldSuffix + '-clear"]') ||
            root.querySelector('input[type="checkbox"][name="' + fieldSuffix + '-clear"]');
        if (clear && clear.checked) return false;

        var links = root.querySelectorAll('a[href]');
        for (var i = 0; i < links.length; i++) {
            var href = links[i].getAttribute('href') || '';
            if (!href || href === '#') continue;
            if (href.indexOf(DEFAULT_IMAGE) !== -1) continue;
            return true;
        }
        return false;
    }

    function clearMarks(form) {
        form.querySelectorAll('.' + CLS.field).forEach(function (el) {
            el.classList.remove(CLS.field);
        });
        form.querySelectorAll('.' + CLS.row).forEach(function (el) {
            el.classList.remove(CLS.row);
        });
        form.querySelectorAll('.' + CLS.msg).forEach(function (el) {
            el.remove();
        });
        var banner = form.querySelector('.' + CLS.banner);
        if (banner) banner.remove();
    }

    function markInvalid(el, message) {
        if (!el) return null;
        el.classList.add(CLS.field);
        var row = el.closest('tr, .form-row');
        if (row) row.classList.add(CLS.row);

        var host =
            el.closest(
                '.related-widget-wrapper, .flex-container, td, .form-row, .selector, .field-box'
            ) || el.parentElement;
        if (host && !host.querySelector('.' + CLS.msg)) {
            var msg = document.createElement('div');
            msg.className = CLS.msg;
            msg.textContent = message || MSG.required;
            host.appendChild(msg);
        }
        return el;
    }

    function pushInvalid(invalids, el, message) {
        var marked = markInvalid(el, message);
        if (marked) invalids.push(marked);
    }

    function showBanner(form, text) {
        var banner = document.createElement('div');
        banner.className = CLS.banner;
        banner.setAttribute('role', 'alert');
        banner.textContent = text;
        var content = form.querySelector('fieldset, .inline-group') || form.firstElementChild;
        if (content && content.parentNode) {
            content.parentNode.insertBefore(banner, content);
        } else {
            form.insertBefore(banner, form.firstChild);
        }
    }

    function focusAndScroll(el) {
        if (!el) return;
        try {
            el.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' });
        } catch (e) {
            el.scrollIntoView(true);
        }
        window.setTimeout(function () {
            if (typeof el.focus !== 'function') return;
            try {
                el.focus({ preventScroll: true });
            } catch (err) {
                try {
                    el.focus();
                } catch (err2) {
                    /* non-focusable */
                }
            }
        }, 250);
    }

    function validateTitle(form, invalids) {
        var title = form.querySelector('#id_title');
        if (title && !String(title.value || '').trim()) {
            pushInvalid(invalids, title, MSG.required);
        }
    }

    function validateCatalogImage(form, invalids) {
        var image = form.querySelector('#id_image');
        if (!image) return;
        var wrap =
            image.closest('.form-row, .flex-container, .field-image, .field-box') ||
            image.parentElement;
        if (controlHasValue(image) || hasExistingFile(wrap, 'image')) return;
        pushInvalid(invalids, image, MSG.needImage);
    }

    function validateCategories(form, invalids) {
        var toSelect = form.querySelector('#id_categories_to');
        var multi = form.querySelector('#id_categories');
        var selected = 0;

        if (toSelect) {
            selected = toSelect.options ? toSelect.options.length : 0;
        } else if (multi) {
            selected = Array.prototype.filter.call(multi.options || [], function (o) {
                return o.selected && o.value;
            }).length;
        } else {
            return;
        }

        if (selected >= 1) return;

        var anchor =
            form.querySelector('#id_categories_from') ||
            multi ||
            form.querySelector('.field-categories');
        pushInvalid(invalids, anchor, MSG.needCategory);
    }

    function validateAttrRow(row, invalids) {
        var customEl = findField(row, 'custom_attribute');
        var isCustom = !!(customEl && customEl.checked);
        var qty = findField(row, 'quantity');
        var size = findField(row, 'size');
        var price = findField(row, 'price');
        var customPrice = findField(row, 'custom_price');

        if (qty && !controlHasValue(qty)) {
            pushInvalid(invalids, qty, MSG.required);
        }
        if (isCustom) {
            if (customPrice && !controlHasValue(customPrice)) {
                pushInvalid(invalids, customPrice, MSG.required);
            }
        } else {
            if (size && !controlHasValue(size)) {
                pushInvalid(invalids, size, MSG.required);
            }
            if (price && !controlHasValue(price)) {
                pushInvalid(invalids, price, MSG.required);
            }
        }
    }

    function validateAttrGroup(form, invalids) {
        var filled = 0;
        eachInlineRow(form, 'product_attr-group', function (row) {
            filled += 1;
            validateAttrRow(row, invalids);
        });
        if (filled >= 1) return;

        var group = form.querySelector('#product_attr-group');
        var anchor =
            (group &&
                (group.querySelector('.add-row a') ||
                    group.querySelector('select[name$="-size"]') ||
                    group.querySelector('h2'))) ||
            group;
        pushInvalid(invalids, anchor, MSG.needAttr);
    }

    function validateImageRow(row, invalids) {
        var image = findField(row, 'image');
        if (!image) return;
        if (controlHasValue(image) || hasExistingFile(row, 'image')) return;
        pushInvalid(invalids, image, MSG.required);
    }

    function validateRelatedRow(row, invalids) {
        var product =
            row.querySelector('select[name$="-product"]') ||
            row.querySelector('input[name$="-product"]:not([type="hidden"])');
        if (product && !controlHasValue(product)) {
            pushInvalid(invalids, product, MSG.required);
        }
    }

    function validateSpecRow(row, invalids) {
        var spec = findField(row, 'specification');
        var value = findField(row, 'spec_value');
        var hasSpec = spec && controlHasValue(spec);
        var hasValue = value && controlHasValue(value);
        if (!hasSpec && !hasValue) return;
        if (spec && !hasSpec) pushInvalid(invalids, spec, MSG.required);
        if (value && !hasValue) pushInvalid(invalids, value, MSG.required);
    }

    function validateForm(form) {
        clearMarks(form);
        var invalids = [];
        validateTitle(form, invalids);
        validateCatalogImage(form, invalids);
        validateCategories(form, invalids);
        validateAttrGroup(form, invalids);
        eachInlineRow(form, 'images-group', function (row) {
            validateImageRow(row, invalids);
        });
        eachInlineRow(form, 'related_products-group', function (row) {
            validateRelatedRow(row, invalids);
        });
        eachInlineRow(form, 'product_specs-group', function (row) {
            validateSpecRow(row, invalids);
        });
        return invalids;
    }

    function clearErrorOnFix(el) {
        if (!el || !el.classList || !el.classList.contains(CLS.field)) return;
        // links / headings used as anchors: clear on any change nearby via change bubbling
        if (el.tagName === 'A' || el.tagName === 'H2') {
            el.classList.remove(CLS.field);
        } else if (!controlHasValue(el)) {
            return;
        } else {
            el.classList.remove(CLS.field);
        }

        var row = el.closest('tr, .form-row');
        if (row && !row.querySelector('.' + CLS.field)) {
            row.classList.remove(CLS.row);
        }
        var host = el.closest(
            '.related-widget-wrapper, .flex-container, td, .form-row, .selector, .field-box'
        );
        if (host) {
            var msg = host.querySelector('.' + CLS.msg);
            if (msg) msg.remove();
        }
    }

    function onSubmit(event) {
        var form = event.target;
        if (!form || form.id !== 'product_form') return;

        var invalids = validateForm(form);
        if (!invalids.length) return;

        event.preventDefault();
        event.stopPropagation();
        showBanner(
            form,
            invalids.length === 1 ? MSG.bannerOne : MSG.bannerMany(invalids.length)
        );
        focusAndScroll(invalids[0]);
    }

    ready(function () {
        var form = document.getElementById('product_form');
        if (!form) return;
        form.addEventListener('submit', onSubmit, true);
        form.addEventListener('input', function (e) {
            clearErrorOnFix(e.target);
        });
        form.addEventListener('change', function (e) {
            clearErrorOnFix(e.target);
        });
    });
})();
