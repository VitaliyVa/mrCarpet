'use strict';

(function () {
    var ENDPOINT = '/admin/catalog/product/generate-images/';
    var SIZE_LOOKUP = '/admin/catalog/product/scene-size/';
    var INLINE_GROUP_ID = 'images-group';
    var ATTR_GROUP_ID = 'productattribute-group';
    var MAX_SIZE = 15 * 1024 * 1024;
    var ALLOWED = ['image/jpeg', 'image/png', 'image/webp'];
    var LOG_PREFIX = '[scene-size]';
    var DEBUG = true; // тимчасово для діагностики — потім вимкнемо

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

    function log() {
        if (!DEBUG) return;
        var args = Array.prototype.slice.call(arguments);
        args.unshift(LOG_PREFIX);
        console.log.apply(console, args);
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

    function collectDomSizeCandidates() {
        var candidates = [];
        var selectors = [
            '#' + ATTR_GROUP_ID + ' select[name$="-size"]',
            'select[name^="productattribute-"][name$="-size"]',
            'select[id^="id_productattribute-"][id$="-size"]',
            '.inline-group select[name$="-size"]',
        ];
        var seen = {};
        selectors.forEach(function (sel) {
            document.querySelectorAll(sel).forEach(function (el) {
                if (seen[el.name || el.id]) return;
                seen[el.name || el.id] = true;
                var row = el.closest('tr');
                var deleted = row ? rowIsDeleted(row) : false;
                var isEmpty = row && row.classList.contains('empty-form');
                var opt = el.options && el.selectedIndex >= 0 ? el.options[el.selectedIndex] : null;
                var text = opt ? String(opt.text || '') : '';
                candidates.push({
                    name: el.name || '',
                    id: el.id || '',
                    value: el.value || '',
                    text: text.replace(/\u00a0/g, ' ').trim(),
                    deleted: deleted,
                    emptyForm: !!isEmpty,
                    tag: el.tagName,
                    className: el.className || '',
                });
            });
        });
        return candidates;
    }

    function getFirstSizeLabelFromDom() {
        var candidates = collectDomSizeCandidates();
        log('DOM size candidates:', candidates);
        log('ATTR group exists:', !!document.getElementById(ATTR_GROUP_ID));
        log('inline-group count:', document.querySelectorAll('.inline-group').length);
        log(
            'inline-group ids:',
            Array.prototype.map.call(document.querySelectorAll('.inline-group'), function (el) {
                return el.id;
            })
        );

        for (var i = 0; i < candidates.length; i++) {
            var c = candidates[i];
            if (c.deleted || c.emptyForm) continue;
            if (!c.value) continue;
            if (isBlankSizeText(c.text)) continue;
            log('DOM first size chosen:', c);
            return c.text;
        }
        return null;
    }

    function getCachedServerSize(block) {
        return (block.dataset.sceneSizeLabel || '').trim() || null;
    }

    function setCachedServerSize(block, label, meta) {
        if (label) {
            block.dataset.sceneSizeLabel = label;
            block.dataset.sceneSizeMeta = JSON.stringify(meta || {});
        } else {
            delete block.dataset.sceneSizeLabel;
            delete block.dataset.sceneSizeMeta;
        }
    }

    function renderSizeDebug(block, extra) {
        var box = block.querySelector('.replicate-size-debug');
        if (!box) return;
        var payload = {
            productId: getProductId(),
            pathname: window.location.pathname,
            cachedServerSize: getCachedServerSize(block),
            domSize: null,
            domCandidates: collectDomSizeCandidates(),
            attrGroupId: ATTR_GROUP_ID,
            attrGroupFound: !!document.getElementById(ATTR_GROUP_ID),
            inlineGroupIds: Array.prototype.map.call(
                document.querySelectorAll('.inline-group'),
                function (el) { return el.id; }
            ),
            extra: extra || null,
        };
        // avoid recursive log spam from collect inside getFirst...
        var first = null;
        for (var i = 0; i < payload.domCandidates.length; i++) {
            var c = payload.domCandidates[i];
            if (!c.deleted && !c.emptyForm && c.value && !isBlankSizeText(c.text)) {
                first = c.text;
                break;
            }
        }
        payload.domSize = first;
        box.hidden = false;
        box.textContent = JSON.stringify(payload, null, 2);
        log('debug panel updated', payload);
    }

    function applySizeGate(block, sizeLabel, source) {
        var info = block.querySelector('.replicate-size-info');
        var btn = block.querySelector('.replicate-generate-btn');
        var fileInput = block.querySelector('.replicate-source-input');
        var hasSize = !!sizeLabel;

        if (hasSize) {
            info.className = 'replicate-size-info replicate-size-ok';
            info.textContent =
                'Масштаб у промпті: ' + sizeLabel +
                (source ? ' [' + source + ']' : '') +
                '.';
            btn.disabled = false;
            fileInput.disabled = false;
        } else {
            info.className = 'replicate-size-info replicate-size-missing';
            info.textContent =
                'Генерація заблокована: додайте хоча б один розмір у «Варіації → Розмір»' +
                (getProductId() ? ' і збережіть товар.' : ' (спочатку збережіть товар з розміром).') +
                ' Див. діагностику нижче / Console [scene-size].';
            btn.disabled = true;
            fileInput.disabled = true;
        }
        renderSizeDebug(block, { appliedSource: source || null, appliedSize: sizeLabel || null });
        return hasSize ? sizeLabel : null;
    }

    function updateSizeGate(block) {
        var serverLabel = getCachedServerSize(block);
        if (serverLabel) {
            return applySizeGate(block, serverLabel, 'server');
        }
        var domLabel = getFirstSizeLabelFromDom();
        if (domLabel) {
            return applySizeGate(block, domLabel, 'dom');
        }
        return applySizeGate(block, null, null);
    }

    function fetchServerSize(block) {
        var productId = getProductId();
        if (!productId) {
            log('no productId in URL — skip server lookup');
            updateSizeGate(block);
            return Promise.resolve(null);
        }
        var url = SIZE_LOOKUP + '?product_id=' + encodeURIComponent(productId) + '&debug=1';
        log('fetching', url);
        return fetch(url, { credentials: 'same-origin' })
            .then(function (res) {
                return res.json().then(function (data) {
                    log('server response', res.status, data);
                    if (data && data.success && data.size_label) {
                        setCachedServerSize(block, data.size_label, data);
                        applySizeGate(block, data.size_label, 'server:' + (data.source || 'db'));
                        return data.size_label;
                    }
                    setCachedServerSize(block, null);
                    updateSizeGate(block);
                    renderSizeDebug(block, { server: data });
                    return null;
                });
            })
            .catch(function (err) {
                log('server lookup failed', err);
                updateSizeGate(block);
                renderSizeDebug(block, { fetchError: String(err && err.message || err) });
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

    function runSceneGeneration(file, options, productId, sizeLabel) {
        var formData = new FormData();
        formData.append('source_image', file);
        formData.append('phase', 'scene');
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
            'У промпт підставляється <b>перший розмір</b> з «Варіації → Розмір» (як на вітрині). ' +
            'Результат потрапить у перший порожній рядок «Зображення продуктів» нижче.' +
            '</p>' +
            '<div class="replicate-size-info" aria-live="polite"></div>' +
            '<details class="replicate-size-debug-wrap"><summary>Діагностика розміру (скинь сюди / Console)</summary>' +
            '<pre class="replicate-size-debug" hidden></pre></details>' +
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
        var productId = getProductId();

        setProgress(
            block,
            'Генерація сцени…',
            'Масштаб: ' + sizeLabel + '. Replicate створює інтер\'єр (~1–3 хв). Не закривайте сторінку.',
            true
        );

        runSceneGeneration(file, options, productId, sizeLabel)
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
                block.querySelectorAll('.replicate-scene-options input').forEach(function (el) {
                    el.disabled = false;
                });
                block.classList.remove('is-loading');
                updateSizeGate(block);
            });
    }

    function bindSizeWatchers(block) {
        document.addEventListener('change', function (ev) {
            var t = ev.target;
            if (!t || !t.name) return;
            if (t.name.indexOf('productattribute-') === -1) return;
            if (t.name.indexOf('-size') === -1 && t.name.indexOf('-DELETE') === -1) return;
            // DOM змінились — але серверний кеш має пріоритет для збереженого товару
            if (!getCachedServerSize(block)) updateSizeGate(block);
            else renderSizeDebug(block, { domChange: t.name });
        });
    }

    function mountSceneBlock() {
        var inlineGroup = document.getElementById(INLINE_GROUP_ID);
        if (!inlineGroup) {
            log('images-group not found — scene block not mounted');
            return;
        }

        var block = buildBlock();
        inlineGroup.parentNode.insertBefore(block, inlineGroup);

        var fileInput = block.querySelector('.replicate-source-input');
        var btn = block.querySelector('.replicate-generate-btn');
        btn.addEventListener('click', function () {
            onGenerate(block, fileInput, btn);
        });
        bindSizeWatchers(block);
        log('mounted', {
            productId: getProductId(),
            pathname: window.location.pathname,
        });
        // Спочатку DOM (швидко), потім сервер (джерело істини)
        updateSizeGate(block);
        fetchServerSize(block);
    }

    document.addEventListener('DOMContentLoaded', mountSceneBlock);
})();
