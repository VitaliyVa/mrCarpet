'use strict';

(function () {
    var GROUP_ID = 'images-group';
    var ALLOWED = ['image/jpeg', 'image/png', 'image/webp', 'image/gif'];
    var MAX_SIZE = 15 * 1024 * 1024;

    function getGroup() {
        return document.getElementById(GROUP_ID);
    }

    function hasFiles(event) {
        return event.dataTransfer
            && Array.prototype.indexOf.call(event.dataTransfer.types, 'Files') !== -1;
    }

    function isValidImage(file) {
        if (!file || !file.type) return false;
        if (ALLOWED.indexOf(file.type) === -1 && file.type.indexOf('image/') !== 0) return false;
        return file.size <= MAX_SIZE;
    }

    function setFileInput(input, file) {
        var dt = new DataTransfer();
        dt.items.add(file);
        input.files = dt.files;
        input.dispatchEvent(new Event('change', { bubbles: true }));
    }

    function getVisibleImageRows(group) {
        return Array.prototype.slice.call(
            group.querySelectorAll('tbody tr.form-row:not(.empty-form)')
        );
    }

    function rowIsDeleted(row) {
        var del = row.querySelector('input[type="checkbox"][name$="-DELETE"]');
        return del && del.checked;
    }

    function rowHasSavedImage(row) {
        return !!row.querySelector('.image-preview img, a[href*="/media/"]');
    }

    function findEmptyImageInput(group) {
        var rows = getVisibleImageRows(group);
        for (var i = 0; i < rows.length; i++) {
            var row = rows[i];
            if (rowIsDeleted(row) || rowHasSavedImage(row)) continue;
            var input = row.querySelector('input[type="file"][name$="-image"]');
            if (input && (!input.files || !input.files.length)) return input;
        }
        return null;
    }

    function addImageInlineRow(group) {
        var link = group.querySelector('.add-row a');
        if (link) link.click();
    }

    function ensureEmptyImageInput(group) {
        var input = findEmptyImageInput(group);
        if (input) return Promise.resolve(input);

        addImageInlineRow(group);
        return new Promise(function (resolve) {
            var attempts = 0;
            function tryFind() {
                attempts += 1;
                var found = findEmptyImageInput(group);
                if (found) resolve(found);
                else if (attempts < 12) setTimeout(tryFind, 80);
                else resolve(null);
            }
            setTimeout(tryFind, 80);
        });
    }

    function setNextSortOrder(group, targetInput) {
        var row = targetInput.closest('tr');
        if (!row) return;
        var orderInput = row.querySelector('input[name$="-sort_order"]');
        if (!orderInput) return;

        var max = 0;
        group.querySelectorAll('input[name$="-sort_order"]').forEach(function (inp) {
            if (inp === orderInput) return;
            var value = parseInt(inp.value, 10);
            if (!isNaN(value) && value > max) max = value;
        });
        orderInput.value = max + 10;
    }

    function setHintState(hint, message, isError) {
        if (!hint) return;
        hint.textContent = message;
        hint.classList.toggle('is-error', !!isError);
    }

    function resetHint(hint) {
        if (!hint) return;
        hint.classList.remove('is-error');
        hint.textContent = 'Перетягніть фото сюди або оберіть файл у рядку';
    }

    function assignFiles(group, hint, files) {
        var queue = Array.prototype.filter.call(files, isValidImage);
        if (!queue.length) {
            setHintState(hint, 'Дозволені лише зображення JPEG, PNG, WebP або GIF до 15 МБ', true);
            return Promise.resolve();
        }

        setHintState(hint, 'Завантаження ' + queue.length + ' фото…', false);

        return queue.reduce(function (chain, file) {
            return chain.then(function () {
                return ensureEmptyImageInput(group).then(function (input) {
                    if (!input) {
                        throw new Error('Не вистачило рядків. Додайте рядок вручну і повторіть.');
                    }
                    setFileInput(input, file);
                    setNextSortOrder(group, input);
                });
            });
        }, Promise.resolve())
            .then(function () {
                setHintState(
                    hint,
                    'Додано ' + queue.length + ' фото. Не забудьте зберегти товар.',
                    false
                );
                window.setTimeout(function () { resetHint(hint); }, 3200);
            })
            .catch(function (err) {
                setHintState(hint, err.message || 'Не вдалося додати фото', true);
            });
    }

    function injectHint(group) {
        if (group.querySelector('.product-image-drop-hint')) return null;

        var hint = document.createElement('div');
        hint.className = 'product-image-drop-hint';
        hint.textContent = 'Перетягніть фото сюди або оберіть файл у рядку';

        var fieldset = group.querySelector('fieldset');
        var heading = fieldset && fieldset.querySelector('h2');
        if (heading && heading.parentNode) {
            heading.parentNode.insertBefore(hint, heading.nextSibling);
        } else if (fieldset) {
            fieldset.insertBefore(hint, fieldset.firstChild);
        } else {
            group.insertBefore(hint, group.firstChild);
        }

        return hint;
    }

    function initDropzone(group) {
        if (group.dataset.dropzoneReady) return;
        group.dataset.dropzoneReady = '1';

        var hint = injectHint(group);
        var dragDepth = 0;

        function onDragEnter(event) {
            if (!hasFiles(event)) return;
            event.preventDefault();
            dragDepth += 1;
            group.classList.add('is-file-dragover');
        }

        function onDragOver(event) {
            if (!hasFiles(event)) return;
            event.preventDefault();
            event.dataTransfer.dropEffect = 'copy';
        }

        function onDragLeave(event) {
            if (!hasFiles(event)) return;
            dragDepth = Math.max(0, dragDepth - 1);
            if (dragDepth === 0) {
                group.classList.remove('is-file-dragover');
            }
        }

        function onDrop(event) {
            if (!hasFiles(event)) return;
            event.preventDefault();
            event.stopPropagation();
            dragDepth = 0;
            group.classList.remove('is-file-dragover');
            assignFiles(group, hint, event.dataTransfer.files);
        }

        group.addEventListener('dragenter', onDragEnter);
        group.addEventListener('dragover', onDragOver);
        group.addEventListener('dragleave', onDragLeave);
        group.addEventListener('drop', onDrop);
    }

    function init() {
        var group = getGroup();
        if (!group) return;
        initDropzone(group);
    }

    document.addEventListener('DOMContentLoaded', init);
})();
