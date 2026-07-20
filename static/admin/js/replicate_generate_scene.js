'use strict';

(function () {
    var ENDPOINT = '/admin/catalog/product/generate-images/';
    var SIZE_LOOKUP = '/admin/catalog/product/scene-size/';
    var INLINE_GROUP_ID = 'images-group';
    // related_name=product_attr → formset prefix product_attr (не model_name)
    var ATTR_GROUP_ID = 'product_attr-group';
    var ATTR_PREFIX = 'product_attr-';
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
                { value: 'semicircle', label: 'Напівкруг' },
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
                { value: 'bathroom', label: 'Ванна (комплект з 2 килимків)' },
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
    };

    var EXTRA_PROMPT_MAX = 800;

    function getCookie(name) {
        var match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
        return match ? decodeURIComponent(match[2]) : '';
    }

    function getProductId() {
        var match = window.location.pathname.match(/\/catalog\/product\/(\d+)\/change\/?$/);
        return match ? match[1] : null;
    }

    function rowIsDeleted(row) {
        var del = row.querySelector('input[type="checkbox"][name$="-DELETE"]');
        return del && del.checked;
    }

    function isBlankSizeText(text) {
        if (!text) return true;
        text = String(text).replace(/\u00a0/g, ' ').trim();
        if (!text) return true;
        if (text === '---------') return true;
        if (text.indexOf('----') === 0) return true;
        return false;
    }

    function getFirstSizeLabelFromDom() {
        var selects = document.querySelectorAll(
            '#' + ATTR_GROUP_ID + ' select[name$="-size"],' +
            'select[name^="' + ATTR_PREFIX + '"][name$="-size"]'
        );
        for (var i = 0; i < selects.length; i++) {
            var el = selects[i];
            var row = el.closest('tr');
            if (row && (row.classList.contains('empty-form') || rowIsDeleted(row))) continue;
            if (!el.value) continue;
            var opt = el.options[el.selectedIndex];
            var text = ((opt && opt.text) || '').replace(/\u00a0/g, ' ').trim();
            if (isBlankSizeText(text)) continue;
            return text;
        }
        return null;
    }

    function getCachedServerSize(block) {
        return (block.dataset.sceneSizeLabel || '').trim() || null;
    }

    function setCachedServerSize(block, label) {
        if (label) block.dataset.sceneSizeLabel = label;
        else delete block.dataset.sceneSizeLabel;
    }

    function applySizeGate(block, sizeLabel) {
        var info = block.querySelector('.replicate-size-info');
        var btn = block.querySelector('.replicate-generate-btn');
        var fileInput = block.querySelector('.replicate-source-input');
        var hasSize = !!sizeLabel;

        if (hasSize) {
            info.className = 'replicate-size-info replicate-size-ok';
            info.textContent = 'Масштаб у промпті: перший розмір з «Варіації» — ' + sizeLabel + '.';
            btn.disabled = false;
            fileInput.disabled = false;
        } else {
            info.className = 'replicate-size-info replicate-size-missing';
            info.textContent =
                'Генерація заблокована: додайте хоча б один розмір у «Варіації → Розмір»' +
                (getProductId() ? ' і збережіть товар.' : ' (спочатку збережіть товар з розміром).');
            btn.disabled = true;
            fileInput.disabled = true;
        }
        return hasSize ? sizeLabel : null;
    }

    function updateSizeGate(block) {
        var serverLabel = getCachedServerSize(block);
        if (serverLabel) return applySizeGate(block, serverLabel);
        var domLabel = getFirstSizeLabelFromDom();
        if (domLabel) return applySizeGate(block, domLabel);
        return applySizeGate(block, null);
    }

    function fetchServerSize(block) {
        var productId = getProductId();
        if (!productId) {
            updateSizeGate(block);
            return Promise.resolve(null);
        }
        var url = SIZE_LOOKUP + '?product_id=' + encodeURIComponent(productId);
        return fetch(url, { credentials: 'same-origin' })
            .then(function (res) {
                return res.json().then(function (data) {
                    if (data && data.success && data.size_label) {
                        setCachedServerSize(block, data.size_label);
                        applySizeGate(block, data.size_label);
                        return data.size_label;
                    }
                    setCachedServerSize(block, null);
                    updateSizeGate(block);
                    return null;
                });
            })
            .catch(function () {
                updateSizeGate(block);
                return null;
            });
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
        html +=
            '<fieldset class="replicate-option-group replicate-extra-prompt-group">' +
            '<legend>Додатково до промпта</legend>' +
            '<p class="replicate-extra-prompt-hint">' +
            'Необов\'язково. Камера і масштаб підбираються автоматично з розміру варіації. ' +
            'Сюди можна дописати уточнення (наприклад: «килим біля дивана», «більше денного світла»).' +
            '</p>' +
            '<textarea class="replicate-extra-prompt" name="scene_extra_prompt" ' +
            'rows="3" maxlength="' + EXTRA_PROMPT_MAX + '" ' +
            'placeholder="Додаткові вказівки для генерації…"></textarea>' +
            '</fieldset>';
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
        var extra = block.querySelector('.replicate-extra-prompt');
        var extraText = extra ? String(extra.value || '').trim() : '';
        if (extraText) {
            result.extra_prompt = extraText.slice(0, EXTRA_PROMPT_MAX);
        }
        if (result.room_type === 'bathroom') {
            result.second_rug = '1';
            var sizeEl = block.querySelector('.replicate-second-size');
            var sizeText = sizeEl ? String(sizeEl.value || '').trim() : '';
            if (sizeText) result.second_size_label = sizeText.slice(0, 40);
        }
        return result;
    }

    function isBathroom(block) {
        var selected = block.querySelector('input[name="scene_room_type"]:checked');
        return !!selected && selected.value === 'bathroom';
    }

    function syncBathroomUi(block) {
        var extra = block.querySelector('.replicate-bath-extra');
        if (extra) extra.hidden = !isBathroom(block);
    }

    function getSecondFile(block) {
        var input = block.querySelector('.replicate-source-input-2');
        return input && input.files && input.files.length ? input.files[0] : null;
    }

    function setSceneControlsDisabled(block, disabled) {
        block.querySelectorAll('.replicate-scene-options input, .replicate-scene-options textarea').forEach(
            function (el) {
                el.disabled = !!disabled;
            }
        );
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

    function runSceneGeneration(file, options, productId, sizeLabel, secondFile) {
        var formData = new FormData();
        formData.append('source_image', file);
        formData.append('phase', 'scene');
        if (secondFile) formData.append('source_image_2', secondFile);
        if (productId) formData.append('product_id', productId);
        if (sizeLabel) formData.append('size_label', sizeLabel);
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
            'У промпт підставляється <b>перший розмір</b> з «Варіації → Розмір»; ' +
            'відстань камери підбирається автоматично за розміром. ' +
            'Результат потрапить у перший порожній рядок «Зображення продуктів» нижче.' +
            '</p>' +
            '<div class="replicate-size-info" aria-live="polite"></div>' +
            buildOptionsHtml() +
            '<div class="replicate-generate-controls">' +
            '<input type="file" accept="image/jpeg,image/png,image/webp" class="replicate-source-input" />' +
            '<button type="button" class="replicate-generate-btn">Згенерувати сцену</button>' +
            '</div>' +
            '<div class="replicate-bath-extra" hidden style="margin:10px 0;padding:10px 12px;' +
            'background:#f7efe6;border:1px solid #d4b896;border-radius:6px">' +
            '<div style="margin-bottom:6px"><b>Ванна кімната — комплект з 2 килимків</b></div>' +
            '<div style="font-size:12px;color:#5c5652;margin-bottom:8px">' +
            'Перше фото (вище) — килим <b>з вирізом під унітаз</b>. ' +
            'Друге фото (нижче) — <b>прямокутний килимок</b> під двері/раковину. ' +
            'Обидва потраплять в один кадр.' +
            '</div>' +
            '<label style="display:block;margin-bottom:6px">Друге фото (прямокутний килимок)<br>' +
            '<input type="file" accept="image/jpeg,image/png,image/webp" class="replicate-source-input-2" />' +
            '</label>' +
            '<label style="display:block">Розмір другого килимка, м (напр. 0.6 × 0.9)<br>' +
            '<input type="text" class="replicate-second-size" placeholder="0.6 × 0.9" style="width:160px" />' +
            '</label>' +
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
        var sizeLabel = updateSizeGate(block);
        if (!sizeLabel) {
            setStatus(
                block,
                'Спочатку додайте розмір у «Варіації → Розмір» і збережіть товар',
                true
            );
            return;
        }

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

        var secondFile = null;
        if (isBathroom(block)) {
            secondFile = getSecondFile(block);
            if (!secondFile) {
                setStatus(
                    block,
                    'Для ванної потрібне друге фото — прямокутний килимок під двері',
                    true
                );
                return;
            }
            if (ALLOWED.indexOf(secondFile.type) === -1) {
                setStatus(block, 'Друге фото: дозволені лише JPEG, PNG або WebP', true);
                return;
            }
            if (secondFile.size > MAX_SIZE) {
                setStatus(block, 'Друге фото: максимум 15 МБ', true);
                return;
            }
        }

        btn.disabled = true;
        fileInput.disabled = true;
        setSceneControlsDisabled(block, true);
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
        var productId = getProductId();

        setProgress(
            block,
            'Генерація сцени…',
            'Масштаб: ' + sizeLabel + '. Replicate створює інтер\'єр (~1–3 хв). Не закривайте сторінку.',
            true
        );

        runSceneGeneration(file, options, productId, sizeLabel, secondFile)
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
                    var usedSize = optsMeta && optsMeta.size_label ? optsMeta.size_label : sizeLabel;
                    var optsNote = optsMeta
                        ? ' [' + Object.keys(optsMeta).map(function (k) { return k + '=' + optsMeta[k]; }).join(', ') + ']'
                        : '';
                    setStatus(
                        block,
                        'Готово за ' + totalSec + ' с (розмір ' + usedSize + ')' + optsNote +
                        '. Зображення додано в інлайн — натисніть «Зберегти».',
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
                setSceneControlsDisabled(block, false);
                block.classList.remove('is-loading');
                updateSizeGate(block);
            });
    }

    function bindSizeWatchers(block) {
        document.addEventListener('change', function (ev) {
            var t = ev.target;
            if (!t || !t.name) return;
            if (t.name.indexOf(ATTR_PREFIX) !== 0) return;
            if (t.name.indexOf('-size') === -1 && t.name.indexOf('-DELETE') === -1) return;
            if (!getCachedServerSize(block)) updateSizeGate(block);
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
        // Блок другого фото з'являється лише для «Ванна»
        block.addEventListener('change', function (ev) {
            var t = ev.target;
            if (t && t.name === 'scene_room_type') syncBathroomUi(block);
        });
        syncBathroomUi(block);
        bindSizeWatchers(block);
        updateSizeGate(block);
        fetchServerSize(block);
    }

    document.addEventListener('DOMContentLoaded', mountSceneBlock);
})();
