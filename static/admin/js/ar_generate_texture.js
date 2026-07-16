'use strict';

(function () {
    var ENDPOINT = '/admin/catalog/product/generate-ar-texture/';

    function getCookie(name) {
        var match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
        return match ? decodeURIComponent(match[2]) : '';
    }

    function getProductId() {
        var match = window.location.pathname.match(/\/product\/(\d+)\//);
        return match ? match[1] : null;
    }

    function setStatus(el, text, isError) {
        if (!el) return;
        el.textContent = text || '';
        el.style.color = isError ? '#ba2121' : '#417690';
    }

    function init() {
        var btn = document.getElementById('ar-generate-texture-btn');
        var statusEl = document.getElementById('ar-generate-texture-status');
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

            if (!window.confirm('Згенерувати AR-текстуру з каталожного фото? Це займе ~10–60 с.')) {
                return;
            }

            btn.disabled = true;
            setStatus(statusEl, 'Генерація… (Bria product-cutout)', false);

            var body = new FormData();
            body.append('product_id', productId);

            fetch(ENDPOINT, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'X-CSRFToken': getCookie('csrftoken'),
                },
                body: body,
            })
                .then(function (res) {
                    return res.json().then(function (data) {
                        return { ok: res.ok, data: data };
                    });
                })
                .then(function (result) {
                    if (!result.ok || !result.data.success) {
                        var err = (result.data && result.data.error) || 'Помилка генерації';
                        setStatus(statusEl, err, true);
                        btn.disabled = false;
                        return;
                    }
                    setStatus(statusEl, 'Готово. Перезавантажую…', false);
                    window.location.reload();
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
