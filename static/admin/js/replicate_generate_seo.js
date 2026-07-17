'use strict';

(function () {
    var ENDPOINT = '/admin/catalog/product/generate-seo/';

    function getCookie(name) {
        var match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
        return match ? decodeURIComponent(match[2]) : '';
    }

    function getProductId() {
        var match = window.location.pathname.match(/\/product\/(\d+)\//);
        return match ? match[1] : null;
    }

    function field(name) {
        return document.getElementById('id_' + name);
    }

    function isEmpty(el) {
        return !el || !String(el.value || '').trim();
    }

    function setStatus(el, text, isError) {
        if (!el) return;
        el.textContent = text || '';
        el.style.color = isError ? '#ba2121' : '#417690';
    }

    function clearLogs() {
        var box = document.getElementById('seo-generate-logs');
        var content = document.getElementById('seo-generate-logs-content');
        if (content) content.innerHTML = '';
        if (box) box.hidden = true;
    }

    function appendLogs(logs) {
        var box = document.getElementById('seo-generate-logs');
        var content = document.getElementById('seo-generate-logs-content');
        if (!box || !content || !logs || !logs.length) return;

        logs.forEach(function (entry) {
            var line = document.createElement('div');
            var level = (entry && entry.level) || 'info';
            line.className = 'replicate-log-line replicate-log-' + level;
            line.textContent = (entry && entry.text) || String(entry);
            content.appendChild(line);
        });
        box.hidden = false;
        content.scrollTop = content.scrollHeight;
    }

    function applyFields(data) {
        var metaTitle = field('meta_title');
        var metaDesc = field('meta_description');
        var metaKeys = field('meta_keys');
        var description = field('description');

        var seoOccupied =
            !isEmpty(metaTitle) || !isEmpty(metaDesc) || !isEmpty(metaKeys);
        if (seoOccupied) {
            if (!window.confirm('SEO-поля вже заповнені. Перезаписати?')) {
                return false;
            }
        }

        if (metaTitle) metaTitle.value = data.meta_title || '';
        if (metaDesc) metaDesc.value = data.meta_description || '';
        if (metaKeys) metaKeys.value = data.meta_keys || '';

        if (data.fill_description && description && isEmpty(description)) {
            description.value = data.description || '';
        }

        return true;
    }

    function init() {
        var btn = document.getElementById('seo-generate-btn');
        var statusEl = document.getElementById('seo-generate-status');
        if (!btn) return;

        var productId = getProductId();
        if (!productId) {
            btn.disabled = true;
            setStatus(statusEl, 'Збережіть товар перед генерацією', true);
            return;
        }

        btn.addEventListener('click', function (event) {
            event.preventDefault();
            if (btn.disabled) return;

            if (
                !window.confirm(
                    'Згенерувати SEO (і короткий Description, якщо порожній) з каталожного фото? ~5–20 с.'
                )
            ) {
                return;
            }

            btn.disabled = true;
            clearLogs();
            setStatus(statusEl, 'Генерація… (gpt-4o-mini)', false);

            var body = new FormData();
            body.append('product_id', productId);

            fetch(ENDPOINT, {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'X-CSRFToken': getCookie('csrftoken') },
                body: body,
            })
                .then(function (res) {
                    return res.json().then(function (data) {
                        return { ok: res.ok, data: data };
                    });
                })
                .then(function (result) {
                    appendLogs(result.data && result.data.logs);
                    if (!result.ok || !result.data.success) {
                        var err =
                            (result.data && result.data.error) || 'Помилка генерації';
                        setStatus(statusEl, err, true);
                        btn.disabled = false;
                        return;
                    }
                    var applied = applyFields(result.data);
                    if (!applied) {
                        setStatus(statusEl, 'Скасовано (логи вище)', false);
                        btn.disabled = false;
                        return;
                    }
                    var extra = result.data.fill_description
                        ? ' + Description'
                        : ' (Description не чіпали — уже був)';
                    setStatus(
                        statusEl,
                        'Готово за ' +
                            (result.data.duration_sec || '?') +
                            ' с' +
                            extra +
                            '. Перевірте й збережіть товар.',
                        false
                    );
                    btn.disabled = false;
                })
                .catch(function (err) {
                    setStatus(statusEl, String(err), true);
                    btn.disabled = false;
                });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
