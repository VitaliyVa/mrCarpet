'use strict';

(function () {
    var ENDPOINT = '/admin/blog/article/generate-article/';

    function getCookie(name) {
        var match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
        return match ? decodeURIComponent(match[2]) : '';
    }

    /** Only changelist /admin/blog/article/ — not add/change forms. */
    function isArticleChangelist() {
        return /\/admin\/blog\/article\/?$/.test(window.location.pathname);
    }

    function ensureButton() {
        if (!isArticleChangelist()) return;
        var tools = document.querySelector('ul.object-tools');
        if (!tools || document.getElementById('article-generate-btn')) return;

        var li = document.createElement('li');
        var a = document.createElement('a');
        a.href = '#';
        a.id = 'article-generate-btn';
        a.className = 'addlink';
        a.textContent = 'Згенерувати пост (Replicate)';
        a.title = 'Тема → gpt-4o-mini + gpt-image-2 (quality=low)';
        li.appendChild(a);

        var status = document.createElement('span');
        status.id = 'article-generate-status';
        status.style.marginLeft = '12px';
        status.style.fontSize = '13px';
        li.appendChild(status);

        tools.insertBefore(li, tools.firstChild);
    }

    function setStatus(text, isError) {
        var el = document.getElementById('article-generate-status');
        if (!el) return;
        el.textContent = text || '';
        el.style.color = isError ? '#ba2121' : '#417690';
    }

    function init() {
        ensureButton();
        var btn = document.getElementById('article-generate-btn');
        if (!btn) return;

        btn.addEventListener('click', function (event) {
            event.preventDefault();
            if (btn.dataset.busy === '1') return;

            var topic = window.prompt(
                'Тема статті (українською або коротко):\nНаприклад: «Як вибрати розмір килима у вітальню»'
            );
            if (topic === null) return;
            topic = String(topic || '').trim();
            if (topic.length < 3) {
                window.alert('Тема занадто коротка');
                return;
            }

            if (
                !window.confirm(
                    'Згенерувати НОВИЙ пост за темою?\n\n«' +
                        topic +
                        '»\n\nТекст: gpt-4o-mini\nФото: gpt-image-2 (quality=low)\n~30–90 с. Не закривайте вкладку.'
                )
            ) {
                return;
            }

            btn.dataset.busy = '1';
            btn.style.opacity = '0.6';
            setStatus('Генерація тексту… потім фото (low)…', false);

            var body = new FormData();
            body.append('topic', topic);

            fetch(ENDPOINT, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'X-CSRFToken': getCookie('csrftoken'),
                },
                body: body,
            })
                .then(function (res) {
                    return res.text().then(function (raw) {
                        var data = null;
                        try {
                            data = JSON.parse(raw);
                        } catch (e) {
                            throw new Error(
                                res.ok
                                    ? 'Некоректна відповідь сервера'
                                    : 'Помилка сервера (' + res.status + ')'
                            );
                        }
                        return { ok: res.ok, data: data };
                    });
                })
                .then(function (result) {
                    if (!result.data || !result.data.success) {
                        throw new Error(
                            (result.data && result.data.error) || 'Помилка генерації'
                        );
                    }
                    var d = result.data;
                    setStatus(
                        'Готово: #' +
                            d.article_id +
                            ' (текст ' +
                            d.text_duration_sec +
                            'с, фото ' +
                            d.image_duration_sec +
                            'с). Відкриваю…',
                        false
                    );
                    window.location.href = d.edit_url;
                })
                .catch(function (err) {
                    setStatus(err.message || String(err), true);
                    btn.dataset.busy = '0';
                    btn.style.opacity = '1';
                });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
