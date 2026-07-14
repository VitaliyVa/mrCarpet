'use strict';

(function () {
    var ENDPOINT = '/admin/catalog/product/generate-images/';
    var INLINE_GROUP_ID = 'images-group';
    var MAX_SIZE = 15 * 1024 * 1024;
    var ALLOWED = ['image/jpeg', 'image/png', 'image/webp'];

    var SCENE_OPTIONS = {
        rug_shape: {
            label: 'Форма килима',
            name: 'rug_shape',
            default: 'auto',
            choices: [
                { value: 'auto', label: 'Авто (з фото)' },
                { value: 'oval', label: 'Овальний' },
                { value: 'rectangular', label: 'Прямокутний' },
                { value: 'round', label: 'Круглий' },
                { value: 'runner', label: 'Доріжка' },
            ],
        },
        room_type: {
            label: 'Кімната',
            name: 'room_type',
            default: 'auto',
            choices: [
                { value: 'auto', label: 'Авто' },
                { value: 'living_room', label: 'Вітальня' },
                { value: 'bedroom', label: 'Спальня' },
                { value: 'kids_room', label: 'Дитяча' },
                { value: 'dining_room', label: 'Їдальня' },
                { value: 'hallway', label: 'Коридор / передпокій' },
                { value: 'office', label: 'Кабінет' },
            ],
        },
        camera_distance: {
            label: 'Відстань камери',
            name: 'camera_distance',
            default: 'medium',
            choices: [
                { value: 'close', label: 'Зблизька (килим у фокусі)' },
                { value: 'medium', label: 'Середня' },
                { value: 'wide', label: 'Здалека (вся кімната)' },
            ],
        },
        view_angle: {
            label: 'Ракурс',
            name: 'view_angle',
            default: 'eye_level',
            choices: [
                { value: 'eye_level', label: 'На рівні очей' },
                { value: 'high_angle', label: 'Зверху вниз' },
                { value: 'top_down_partial', label: 'Майже зверху' },
            ],
        },
        floor_style: {
            label: 'Підлога',
            name: 'floor_style',
            default: 'auto',
            choices: [
                { value: 'auto', label: 'Авто' },
                { value: 'wood', label: 'Темне дерево' },
                { value: 'light_wood', label: 'Світле дерево' },
                { value: 'tile', label: 'Плитка' },
                { value: 'concrete', label: 'Бетон' },
            ],
        },
        color_mode: {
            label: 'Колір килима',
            name: 'color_mode',
            default: 'auto',
            choices: [
                { value: 'auto', label: 'Авто' },
                { value: 'preserve_exact', label: 'Точно як на фото' },
                { value: 'monochrome', label: 'Монохром' },
            ],
        },
    };

    function getCookie(name) {
        var match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
        return match ? decodeURIComponent(match[2]) : '';
    }

    function buildOptionsHtml() {
        var html = '<div class="replicate-options replicate-scene-options">';
        Object.keys(SCENE_OPTIONS).forEach(function (key) {
            var group = SCENE_OPTIONS[key];
            var groupName = 'scene_' + group.name;
            html += '<fieldset class="replicate-option-group">';
            html += '<legend>' + group.label + '</legend>';
            html += '<div class="replicate-option-radios">';
            group.choices.forEach(function (choice) {
                var id = groupName + '_' + choice.value;
                var checked = choice.value === group.default ? ' checked' : '';
                html +=
                    '<label class="replicate-option-label" for="' + id + '">' +
                    '<input type="radio" id="' + id + '" name="' + groupName + '" value="' + choice.value + '"' + checked + ' />' +
                    '<span>' + choice.label + '</span>' +
                    '</label>';
            });
            html += '</div></fieldset>';
        });
        html += '</div>';
        return html;
    }

    function collectOptions(block) {
        var result = { phase: 'scene' };
        Object.keys(SCENE_OPTIONS).forEach(function (key) {
            var group = SCENE_OPTIONS[key];
            var groupName = 'scene_' + group.name;
            var selected = block.querySelector('input[name="' + groupName + '"]:checked');
            result[group.name] = selected ? selected.value : group.default;
        });
        return result;
    }

    function setNextSortOrder(targetInput) {
        var row = targetInput.closest('tr');
        if (!row) return;
        var orderInput = row.querySelector('input[name$="-sort_order"]');
        if (!orderInput) return;
        var max = 0;
        document.querySelectorAll('#' + INLINE_GROUP_ID + ' input[name$="-sort_order"]').forEach(function (inp) {
            if (inp === orderInput) return;
            var v = parseInt(inp.value, 10);
            if (!isNaN(v) && v > max) max = v;
        });
        orderInput.value = max + 10;
    }

    function setIsAiFlag(targetInput, value) {
        var row = targetInput.closest('tr');
        if (!row) return;
        var checkbox = row.querySelector('input[type="checkbox"][name$="-is_ai"]');
        if (checkbox) {
            checkbox.checked = !!value;
        }
    }

    function setFileInput(input, base64, filename, mime) {
        var binary = atob(base64);
        var bytes = new Uint8Array(binary.length);
        for (var i = 0; i < binary.length; i++) {
            bytes[i] = binary.charCodeAt(i);
        }
        var file = new File([bytes], filename, { type: mime });
        var dt = new DataTransfer();
        dt.items.add(file);
        input.files = dt.files;
        input.dispatchEvent(new Event('change', { bubbles: true }));
    }

    function getVisibleImageRows() {
        var group = document.getElementById(INLINE_GROUP_ID);
        if (!group) return [];
        return Array.prototype.slice.call(
            group.querySelectorAll('tbody tr.form-row:not(.empty-form)')
        );
    }

    function rowHasSavedImage(row) {
        return !!row.querySelector('.image-preview img, a[href*="/media/"]');
    }

    function rowIsDeleted(row) {
        var del = row.querySelector('input[type="checkbox"][name$="-DELETE"]');
        return del && del.checked;
    }

    function findEmptyImageInput() {
        var rows = getVisibleImageRows();
        for (var i = 0; i < rows.length; i++) {
            var row = rows[i];
            if (rowIsDeleted(row) || rowHasSavedImage(row)) continue;
            var input = row.querySelector('input[type="file"][name$="-image"]');
            if (input && (!input.files || !input.files.length)) return input;
        }
        return null;
    }

    function addImageInlineRow() {
        var link = document.querySelector('#' + INLINE_GROUP_ID + ' .add-row a');
        if (link) link.click();
    }

    function ensureEmptyImageInput() {
        var input = findEmptyImageInput();
        if (input) return Promise.resolve(input);
        addImageInlineRow();
        return new Promise(function (resolve) {
            var attempts = 0;
            function tryFind() {
                attempts += 1;
                var found = findEmptyImageInput();
                if (found) resolve(found);
                else if (attempts < 10) setTimeout(tryFind, 80);
                else resolve(null);
            }
            setTimeout(tryFind, 80);
        });
    }

    function formatElapsed(ms) {
        var sec = Math.floor(ms / 1000);
        var m = Math.floor(sec / 60);
        var s = sec % 60;
        return (m > 0 ? m + ' хв ' : '') + s + ' с';
    }

    function renderLogLine(entry) {
        var level = entry.level || 'info';
        return '<div class="replicate-log-line replicate-log-' + level + '">' + (entry.text || '') + '</div>';
    }

    function appendLogs(block, logs) {
        if (!logs || !logs.length) return;
        var box = block.querySelector('.replicate-logs');
        var container = block.querySelector('.replicate-logs-content');
        box.hidden = false;
        logs.forEach(function (entry) {
            container.insertAdjacentHTML('beforeend', renderLogLine(entry));
        });
        container.scrollTop = container.scrollHeight;
    }

    function clearLogs(block) {
        block.querySelector('.replicate-logs-content').innerHTML = '';
        block.querySelector('.replicate-logs').hidden = true;
    }

    function setProgress(block, title, sub, running) {
        block.querySelector('.replicate-progress').hidden = false;
        block.querySelector('.replicate-status').hidden = true;
        block.querySelector('.replicate-progress-text').textContent = title;
        block.querySelector('.replicate-progress-sub').textContent = sub || '';
        block.classList.toggle('is-loading', !!running);
    }

    function setElapsed(block, ms) {
        block.querySelector('.replicate-elapsed').textContent = 'Час: ' + formatElapsed(ms);
    }

    function setStatus(block, text, isError, isSuccess) {
        block.querySelector('.replicate-progress').hidden = true;
        block.classList.remove('is-loading');
        var status = block.querySelector('.replicate-status');
        status.hidden = false;
        var cls = 'replicate-status';
        if (isError) cls += ' replicate-status-error';
        else if (isSuccess) cls += ' replicate-status-success';
        else cls += ' replicate-status-info';
        status.className = cls;
        status.textContent = text;
    }

    function showPreview(block, sourceUrl, resultB64) {
        var preview = block.querySelector('.replicate-preview');
        preview.hidden = false;
        preview.innerHTML =
            '<div class="replicate-preview-grid">' +
            '<div class="replicate-preview-item"><div class="replicate-preview-label">Джерело</div>' +
            '<img src="' + sourceUrl + '" alt="source" /></div>' +
            '<div class="replicate-preview-item"><div class="replicate-preview-label">Сцена</div>' +
            '<img src="data:image/webp;base64,' + resultB64 + '" alt="result" /></div>' +
            '</div>';
    }

    function runSceneGeneration(file, options) {
        var formData = new FormData();
        formData.append('source_image', file);
        formData.append('phase', 'scene');
        Object.keys(options).forEach(function (key) {
            if (key !== 'phase') formData.append(key, options[key]);
        });

        return fetch(ENDPOINT, {
            method: 'POST',
            headers: { 'X-CSRFToken': getCookie('csrftoken') },
            body: formData,
            credentials: 'same-origin',
        }).then(function (res) {
            return res.json().then(function (data) {
                if (!res.ok) {
                    var err = new Error(data.error || 'Помилка сервера');
                    err.logs = data.logs;
                    throw err;
                }
                return data;
            });
        });
    }

    function buildBlock() {
        var block = document.createElement('div');
        block.className = 'replicate-generate-block replicate-scene-block';
        block.innerHTML =
            '<h3>Генерація фото для сторінки товару (інтер\'єр)</h3>' +
            '<p class="replicate-generate-hint">' +
            'Завантажте фото килима — Replicate згенерує lifestyle-знімок у кімнаті (4:3). ' +
            'Результат потрапить у перший порожній рядок «Зображення продуктів» нижче.' +
            '</p>' +
            buildOptionsHtml() +
            '<div class="replicate-generate-controls">' +
            '<input type="file" accept="image/jpeg,image/png,image/webp" class="replicate-source-input" />' +
            '<button type="button" class="replicate-generate-btn">Згенерувати сцену</button>' +
            '</div>' +
            '<div class="replicate-progress" hidden>' +
            '<div class="replicate-spinner"></div>' +
            '<div class="replicate-progress-text"></div>' +
            '<div class="replicate-progress-sub"></div>' +
            '<div class="replicate-elapsed"></div>' +
            '</div>' +
            '<div class="replicate-logs" hidden><div class="replicate-logs-content"></div></div>' +
            '<div class="replicate-status" hidden></div>' +
            '<div class="replicate-preview" hidden></div>';
        return block;
    }

    function onGenerate(block, fileInput, btn) {
        var file = fileInput.files && fileInput.files[0];
        if (!file) {
            setStatus(block, 'Спочатку виберіть фото килима', true);
            return;
        }
        if (ALLOWED.indexOf(file.type) === -1) {
            setStatus(block, 'Дозволені лише JPEG, PNG або WebP', true);
            return;
        }
        if (file.size > MAX_SIZE) {
            setStatus(block, 'Максимальний розмір файлу — 15 МБ', true);
            return;
        }

        btn.disabled = true;
        fileInput.disabled = true;
        block.querySelectorAll('.replicate-scene-options input').forEach(function (el) {
            el.disabled = true;
        });
        clearLogs(block);
        block.querySelector('.replicate-preview').hidden = true;
        block.querySelector('.replicate-status').hidden = true;

        var started = Date.now();
        var elapsedTimer = setInterval(function () {
            setElapsed(block, Date.now() - started);
        }, 1000);
        setElapsed(block, 0);

        var sourceUrl = URL.createObjectURL(file);
        var options = collectOptions(block);

        setProgress(
            block,
            'Генерація сцени…',
            'Replicate створює інтер\'єр (~1–3 хв). Не закривайте сторінку.',
            true
        );

        runSceneGeneration(file, options)
            .then(function (data) {
                appendLogs(block, data.logs);
                var payload = data.image;
                if (!payload) throw new Error('Сервер не повернув зображення');
                return ensureEmptyImageInput().then(function (targetInput) {
                    if (!targetInput) {
                        throw new Error('Не знайдено порожній рядок у «Зображення продуктів». Додайте рядок вручну.');
                    }
                    setFileInput(
                        targetInput,
                        payload.data_base64,
                        payload.filename,
                        payload.content_type
                    );
                    setIsAiFlag(targetInput, true);
                    setNextSortOrder(targetInput);
                    var totalSec = Math.round((Date.now() - started) / 1000);
                    var optsMeta = data.meta && data.meta.prompt_options;
                    var optsNote = optsMeta
                        ? ' [' + Object.keys(optsMeta).map(function (k) { return k + '=' + optsMeta[k]; }).join(', ') + ']'
                        : '';
                    setStatus(
                        block,
                        'Готово за ' + totalSec + ' с' + optsNote + '. Зображення додано в інлайн — натисніть «Зберегти».',
                        false,
                        true
                    );
                    showPreview(block, sourceUrl, payload.data_base64);
                    targetInput.closest('tr').scrollIntoView({ behavior: 'smooth', block: 'center' });
                });
            })
            .catch(function (err) {
                if (err.logs) appendLogs(block, err.logs);
                setStatus(block, err.message || 'Помилка генерації', true);
            })
            .finally(function () {
                clearInterval(elapsedTimer);
                btn.disabled = false;
                fileInput.disabled = false;
                block.querySelectorAll('.replicate-scene-options input').forEach(function (el) {
                    el.disabled = false;
                });
                block.classList.remove('is-loading');
            });
    }

    function mountSceneBlock() {
        var inlineGroup = document.getElementById(INLINE_GROUP_ID);
        if (!inlineGroup) return;

        var block = buildBlock();
        inlineGroup.parentNode.insertBefore(block, inlineGroup);

        var fileInput = block.querySelector('.replicate-source-input');
        var btn = block.querySelector('.replicate-generate-btn');
        btn.addEventListener('click', function () {
            onGenerate(block, fileInput, btn);
        });
    }

    document.addEventListener('DOMContentLoaded', mountSceneBlock);
})();
