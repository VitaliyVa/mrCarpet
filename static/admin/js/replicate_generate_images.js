'use strict';

(function () {
    var ENDPOINT = '/admin/catalog/product/generate-images/';
    var MAX_SIZE = 15 * 1024 * 1024;
    var ALLOWED = ['image/jpeg', 'image/png', 'image/webp'];

    var CATALOG_OPTIONS = {
        rug_shape: {
            label: 'Форма килима',
            name: 'rug_shape',
            default: 'auto',
            choices: [
                { value: 'auto', label: 'Авто (з фото)' },
                { value: 'oval', label: 'Овальний' },
                { value: 'rectangular', label: 'Прямокутний' },
                { value: 'round', label: 'Круглий' },
                { value: 'runner', label: 'Доріжка (runner)' },
            ],
        },
        source_context: {
            label: 'Тип вихідного фото',
            name: 'source_context',
            default: 'auto',
            choices: [
                { value: 'auto', label: 'Авто' },
                { value: 'in_room', label: 'В інтер\'єрі / на підлозі' },
                { value: 'isolated', label: 'Вже на білому фоні' },
            ],
        },
        color_mode: {
            label: 'Колір',
            name: 'color_mode',
            default: 'auto',
            choices: [
                { value: 'auto', label: 'Авто' },
                { value: 'preserve_exact', label: 'Точно як на фото' },
                { value: 'monochrome', label: 'Монохром / сірий' },
            ],
        },
    };

    var HOVER_OPTIONS = {
        rug_shape: CATALOG_OPTIONS.rug_shape,
        color_mode: CATALOG_OPTIONS.color_mode,
    };

    var PHASES = {
        catalog: {
            phase: 'catalog',
            targetId: 'id_image',
            title: 'Генерація каталожного зображення',
            hint: 'Завантажте фото килима і вкажіть форму — Replicate зробить top-down зображення 2:3.',
            button: 'Згенерувати зображення',
            progressTitle: 'Генерація зображення…',
            progressHint: 'Replicate обробляє фото (~1–3 хв). Не закривайте сторінку.',
            successMsg: 'Зображення згенеровано. Перевірте поле нижче і натисніть «Зберегти».',
            previewResultLabel: 'Результат',
            options: CATALOG_OPTIONS,
        },
        hover: {
            phase: 'hover',
            targetId: 'id_hover_image',
            title: 'Генерація зображення при наведенні',
            hint: 'Завантажте фото килима — Replicate зробить hover-фото (macro, згин, bokeh).',
            button: 'Згенерувати зображення при наведенні',
            progressTitle: 'Генерація hover-зображення…',
            progressHint: 'Replicate обробляє фото (~1–3 хв). Не закривайте сторінку.',
            successMsg: 'Hover-зображення згенеровано. Перевірте поле нижче і натисніть «Зберегти».',
            previewResultLabel: 'Результат',
            options: HOVER_OPTIONS,
        },
    };

    function getCookie(name) {
        var match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
        return match ? decodeURIComponent(match[2]) : '';
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

    function buildOptionsHtml(optionsConfig, phase) {
        if (!optionsConfig) return '';

        var groups = Object.keys(optionsConfig);
        var html = '<div class="replicate-options">';

        groups.forEach(function (key) {
            var group = optionsConfig[key];
            var groupName = phase + '_' + group.name;
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

    function collectOptions(block, cfg) {
        var result = {};
        if (!cfg.options) return result;

        Object.keys(cfg.options).forEach(function (key) {
            var group = cfg.options[key];
            var groupName = cfg.phase + '_' + group.name;
            var selected = block.querySelector('input[name="' + groupName + '"]:checked');
            result[group.name] = selected ? selected.value : group.default;
        });

        return result;
    }

    function buildBlock(cfg) {
        var block = document.createElement('div');
        block.className = 'replicate-generate-block';
        block.dataset.phase = cfg.phase;
        block.innerHTML =
            '<h3>' + cfg.title + '</h3>' +
            '<p class="replicate-generate-hint">' + cfg.hint + '</p>' +
            buildOptionsHtml(cfg.options, cfg.phase) +
            '<div class="replicate-generate-controls">' +
            '<input type="file" accept="image/jpeg,image/png,image/webp" class="replicate-source-input" />' +
            '<button type="button" class="replicate-generate-btn">' + cfg.button + '</button>' +
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

    function formatElapsed(ms) {
        var sec = Math.floor(ms / 1000);
        var m = Math.floor(sec / 60);
        var s = sec % 60;
        return (m > 0 ? m + ' хв ' : '') + s + ' с';
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

    function renderLogLine(entry) {
        var level = 'info';
        var text = '';
        if (typeof entry === 'string') {
            text = entry;
            if (text.indexOf('ERROR') > -1) level = 'error';
            else if (text.indexOf('готово') > -1) level = 'ok';
        } else {
            level = entry.level || 'info';
            text = entry.text || '';
        }
        return '<div class="replicate-log-line replicate-log-' + level + '">' + text + '</div>';
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

    function showPreview(block, sourceUrl, resultB64, resultLabel) {
        var preview = block.querySelector('.replicate-preview');
        preview.hidden = false;
        preview.innerHTML =
            '<div class="replicate-preview-grid">' +
            '<div class="replicate-preview-item"><div class="replicate-preview-label">Джерело</div>' +
            '<img src="' + sourceUrl + '" alt="source" /></div>' +
            '<div class="replicate-preview-item"><div class="replicate-preview-label">' + resultLabel + '</div>' +
            '<img src="data:image/webp;base64,' + resultB64 + '" alt="result" /></div>' +
            '</div>';
    }

    function runPhase(file, phase, options) {
        var formData = new FormData();
        formData.append('source_image', file);
        formData.append('phase', phase);

        Object.keys(options || {}).forEach(function (key) {
            formData.append(key, options[key]);
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

    function onGenerate(block, cfg, fileInput, btn) {
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

        var targetInput = document.getElementById(cfg.targetId);
        if (!targetInput) {
            setStatus(block, 'Не знайдено поле зображення на формі', true);
            return;
        }

        btn.disabled = true;
        fileInput.disabled = true;
        block.querySelectorAll('.replicate-options input').forEach(function (el) {
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
        var promptOptions = collectOptions(block, cfg);

        setProgress(block, cfg.progressTitle, cfg.progressHint, true);

        runPhase(file, cfg.phase, promptOptions)
            .then(function (data) {
                appendLogs(block, data.logs);
                var payload = cfg.phase === 'catalog' ? data.image : data.hover_image;
                if (!payload) {
                    throw new Error('Сервер не повернув зображення');
                }
                setFileInput(targetInput, payload.data_base64, payload.filename, payload.content_type);
                var totalSec = Math.round((Date.now() - started) / 1000);
                var optsMeta = data.meta && data.meta.prompt_options;
                var optsNote = optsMeta ? ' [' + Object.keys(optsMeta).map(function (k) { return k + '=' + optsMeta[k]; }).join(', ') + ']' : '';
                setStatus(block, 'Готово за ' + totalSec + ' с' + optsNote + '. ' + cfg.successMsg, false, true);
                showPreview(block, sourceUrl, payload.data_base64, cfg.previewResultLabel);
            })
            .catch(function (err) {
                if (err.logs) appendLogs(block, err.logs);
                setStatus(block, err.message || 'Помилка генерації', true);
            })
            .finally(function () {
                clearInterval(elapsedTimer);
                btn.disabled = false;
                fileInput.disabled = false;
                block.querySelectorAll('.replicate-options input').forEach(function (el) {
                    el.disabled = false;
                });
                block.classList.remove('is-loading');
            });
    }

    function mountBlock(fieldSelector, cfg) {
        var row = document.querySelector(fieldSelector);
        if (!row || !row.parentNode) return;

        var block = buildBlock(cfg);
        row.parentNode.insertBefore(block, row);

        var fileInput = block.querySelector('.replicate-source-input');
        var btn = block.querySelector('.replicate-generate-btn');
        btn.addEventListener('click', function () {
            onGenerate(block, cfg, fileInput, btn);
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        mountBlock('.form-row.field-image', PHASES.catalog);
        mountBlock('.form-row.field-hover_image', PHASES.hover);
    });
})();
