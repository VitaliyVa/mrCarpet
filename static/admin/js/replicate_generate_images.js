'use strict';

(function () {
    var ENDPOINT = '/admin/catalog/product/generate-images/';
    var MAX_SIZE = 15 * 1024 * 1024;
    var ALLOWED = ['image/jpeg', 'image/png', 'image/webp'];

    var STEPS = {
        catalog: {
            num: 1,
            title: 'Генерація каталожного зображення',
            hint: 'Replicate обробляє фото (~1–3 хв). Не закривайте сторінку.',
        },
        hover: {
            num: 2,
            title: 'Генерація зображення при наведенні',
            hint: 'Другий запит до Replicate (~1–3 хв).',
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

    function buildBlock() {
        var block = document.createElement('div');
        block.className = 'replicate-generate-block';
        block.innerHTML =
            '<h3>Генерація зображень через Replicate</h3>' +
            '<p class="replicate-generate-hint">' +
            'Завантажте фото килима — буде згенеровано 2 зображення окремими запитами. ' +
            'Перевірте результат у полях нижче і натисніть «Зберегти».' +
            '</p>' +
            '<div class="replicate-generate-controls">' +
            '<input type="file" accept="image/jpeg,image/png,image/webp" class="replicate-source-input" />' +
            '<button type="button" class="replicate-generate-btn">Згенерувати зображення та зображення при наведенні</button>' +
            '</div>' +
            '<div class="replicate-progress" hidden>' +
            '<div class="replicate-spinner"></div>' +
            '<div class="replicate-progress-text"></div>' +
            '<div class="replicate-progress-sub"></div>' +
            '<div class="replicate-elapsed"></div>' +
            '</div>' +
            '<div class="replicate-logs" hidden><pre class="replicate-logs-content"></pre></div>' +
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
        var progress = block.querySelector('.replicate-progress');
        var status = block.querySelector('.replicate-status');
        progress.hidden = false;
        status.hidden = true;
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

    function showPreview(block, sourceUrl, imageB64, hoverB64) {
        var preview = block.querySelector('.replicate-preview');
        preview.hidden = false;
        var html = '<div class="replicate-preview-grid">';
        html += '<div class="replicate-preview-item"><div class="replicate-preview-label">Джерело</div><img src="' + sourceUrl + '" alt="source" /></div>';
        if (imageB64) {
            html += '<div class="replicate-preview-item"><div class="replicate-preview-label">Зображення</div><img src="data:image/webp;base64,' + imageB64 + '" alt="catalog" /></div>';
        }
        if (hoverB64) {
            html += '<div class="replicate-preview-item"><div class="replicate-preview-label">При наведенні</div><img src="data:image/webp;base64,' + hoverB64 + '" alt="hover" /></div>';
        }
        html += '</div>';
        preview.innerHTML = html;
    }

    function runPhase(file, phase) {
        var formData = new FormData();
        formData.append('source_image', file);
        formData.append('phase', phase);

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
                    err.phase = phase;
                    throw err;
                }
                return data;
            });
        });
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

        var imageInput = document.getElementById('id_image');
        var hoverInput = document.getElementById('id_hover_image');
        if (!imageInput || !hoverInput) {
            setStatus(block, 'Не знайдено поля зображень на формі', true);
            return;
        }

        btn.disabled = true;
        fileInput.disabled = true;
        clearLogs(block);
        block.querySelector('.replicate-preview').hidden = true;
        block.querySelector('.replicate-status').hidden = true;

        var totalStart = Date.now();
        var elapsedTimer = setInterval(function () {
            setElapsed(block, Date.now() - totalStart);
        }, 1000);
        setElapsed(block, 0);

        var catalogB64 = null;
        var hoverB64 = null;
        var sourceUrl = URL.createObjectURL(file);

        function runStep(phase) {
            var step = STEPS[phase];
            setProgress(
                block,
                'Крок ' + step.num + '/2: ' + step.title,
                step.hint,
                true
            );

            return runPhase(file, phase).then(function (data) {
                appendLogs(block, data.logs);
                if (phase === 'catalog' && data.image) {
                    catalogB64 = data.image.data_base64;
                    setFileInput(imageInput, data.image.data_base64, data.image.filename, data.image.content_type);
                }
                if (phase === 'hover' && data.hover_image) {
                    hoverB64 = data.hover_image.data_base64;
                    setFileInput(hoverInput, data.hover_image.data_base64, data.hover_image.filename, data.hover_image.content_type);
                }
                return data;
            });
        }

        runStep('catalog')
            .then(function () {
                setProgress(block, 'Крок 2/2: Генерація зображення при наведенні', STEPS.hover.hint, true);
                return runStep('hover');
            })
            .then(function (data) {
                var totalSec = Math.round((Date.now() - totalStart) / 1000);
                setStatus(
                    block,
                    'Готово за ' + totalSec + ' с. Обидва зображення згенеровано. Перевірте поля нижче і натисніть «Зберегти».',
                    false,
                    true
                );
                showPreview(block, sourceUrl, catalogB64, hoverB64);
            })
            .catch(function (err) {
                if (err.logs) appendLogs(block, err.logs);
                var phaseLabel = err.phase === 'hover' ? ' (hover)' : err.phase === 'catalog' ? ' (каталог)' : '';
                setStatus(block, (err.message || 'Помилка генерації') + phaseLabel, true);
            })
            .finally(function () {
                clearInterval(elapsedTimer);
                btn.disabled = false;
                fileInput.disabled = false;
                block.classList.remove('is-loading');
            });
    }

    document.addEventListener('DOMContentLoaded', function () {
        var imageRow = document.querySelector('.form-row.field-image');
        if (!imageRow || !imageRow.parentNode) return;

        var block = buildBlock();
        imageRow.parentNode.insertBefore(block, imageRow);

        var fileInput = block.querySelector('.replicate-source-input');
        var btn = block.querySelector('.replicate-generate-btn');

        btn.addEventListener('click', function () {
            onGenerate(block, fileInput, btn);
        });
    });
})();
