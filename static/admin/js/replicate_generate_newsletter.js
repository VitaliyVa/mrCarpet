'use strict';

(function () {
    function getCookie(name) {
        var match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
        return match ? decodeURIComponent(match[2]) : '';
    }

    function campaignId() {
        var root = document.querySelector('.newsletter-admin-actions');
        return root ? root.getAttribute('data-campaign-id') : '';
    }

    function setStatus(text, isError) {
        var el = document.getElementById('newsletter-admin-status');
        if (!el) return;
        el.textContent = text || '';
        el.style.color = isError ? '#ba2121' : '#417690';
    }

    function post(url, formFields) {
        var body = new FormData();
        if (formFields) {
            Object.keys(formFields).forEach(function (k) {
                body.append(k, formFields[k]);
            });
        }
        return fetch(url, {
            method: 'POST',
            headers: { 'X-CSRFToken': getCookie('csrftoken') },
            body: body,
            credentials: 'same-origin',
        }).then(function (res) {
            return res.json().then(function (data) {
                return { ok: res.ok, data: data };
            });
        });
    }

    function bind() {
        var id = campaignId();
        if (!id) return;

        var genBtn = document.getElementById('newsletter-generate-btn');
        var testBtn = document.getElementById('newsletter-test-btn');
        var sendBtn = document.getElementById('newsletter-send-btn');

        if (genBtn) {
            genBtn.addEventListener('click', function (event) {
                event.preventDefault();
                if (genBtn.dataset.busy === '1') return;
                if (
                    !window.confirm(
                        'Згенерувати HTML через Replicate (gpt-4o-mini)?\n' +
                            'Бриф має бути заповнений. 30–90 с, не закривайте вкладку.'
                    )
                ) {
                    return;
                }
                genBtn.dataset.busy = '1';
                genBtn.style.opacity = '0.6';
                setStatus('Генеруємо HTML…', false);
                var subjectEl = document.getElementById('id_subject');
                var preheaderEl = document.getElementById('id_preheader');
                var briefEl = document.getElementById('id_brief');
                post('/admin/project/newslettercampaign/' + id + '/generate-html/', {
                    subject: subjectEl ? subjectEl.value : '',
                    preheader: preheaderEl ? preheaderEl.value : '',
                    brief: briefEl ? briefEl.value : '',
                })
                    .then(function (result) {
                        if (!result.ok || !result.data.success) {
                            throw new Error(
                                (result.data && result.data.error) || 'Помилка генерації'
                            );
                        }
                        var body = document.getElementById('id_body_html');
                        var subject = document.getElementById('id_subject');
                        var preheader = document.getElementById('id_preheader');
                        if (body) body.value = result.data.body_html || '';
                        if (subject && result.data.subject) subject.value = result.data.subject;
                        if (preheader && result.data.preheader) {
                            preheader.value = result.data.preheader;
                        }
                        setStatus(
                            'Готово за ' +
                                (result.data.duration_sec || '?') +
                                ' с (' +
                                (result.data.model || '') +
                                '). Збережіть форму.',
                            false
                        );
                    })
                    .catch(function (err) {
                        setStatus(err.message || String(err), true);
                    })
                    .finally(function () {
                        genBtn.dataset.busy = '0';
                        genBtn.style.opacity = '1';
                    });
            });
        }

        if (testBtn) {
            testBtn.addEventListener('click', function (event) {
                event.preventDefault();
                var emailInput = document.getElementById('id_test_email');
                var email = emailInput ? emailInput.value.trim() : '';
                if (!email) {
                    email = window.prompt('Email для тесту:') || '';
                }
                if (!email) return;
                setStatus('Надсилаємо тест…', false);
                post('/admin/project/newslettercampaign/' + id + '/test-send/', {
                    email: email,
                })
                    .then(function (result) {
                        if (!result.ok || !result.data.success) {
                            throw new Error(
                                (result.data && result.data.error) || 'Помилка тесту'
                            );
                        }
                        setStatus(result.data.message || 'Тест надіслано', false);
                    })
                    .catch(function (err) {
                        setStatus(err.message || String(err), true);
                    });
            });
        }

        if (sendBtn) {
            sendBtn.addEventListener('click', function (event) {
                event.preventDefault();
                if (
                    !window.confirm(
                        'Надіслати кампанію ВСІМ активним підписникам?\n' +
                            'Це запустить фонову відправку через SMTP.'
                    )
                ) {
                    return;
                }
                setStatus('Запускаємо розсилку…', false);
                post('/admin/project/newslettercampaign/' + id + '/mass-send/')
                    .then(function (result) {
                        if (!result.ok || !result.data.success) {
                            throw new Error(
                                (result.data && result.data.error) || 'Помилка відправки'
                            );
                        }
                        setStatus(result.data.message || 'Запущено', false);
                        window.setTimeout(function () {
                            window.location.reload();
                        }, 1200);
                    })
                    .catch(function (err) {
                        setStatus(err.message || String(err), true);
                    });
            });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bind);
    } else {
        bind();
    }
})();
