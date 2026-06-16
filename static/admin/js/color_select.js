'use strict';
/*
 * Покращення select-а «Активний колір» у адмінці:
 *  - кружечок-прев'ю кольору/текстури в кожній опції (templateResult);
 *  - пошук за HEX-кодом: якщо у пошук вставити #rrggbb (або rgb/3-знаковий),
 *    показуються всі кольори, відсортовані за близькістю до введеного кольору.
 * Працює поверх Django-bundled select2. Якщо select2 недоступний — нічого не робимо
 * (звичайний нативний select лишається повністю робочим).
 */
(function () {
    function parseHex(s) {
        if (!s) return null;
        s = String(s).trim().replace(/^#/, '');
        if (/^[0-9a-fA-F]{3}$/.test(s)) {
            s = s.split('').map(function (c) { return c + c; }).join('');
        }
        if (!/^[0-9a-fA-F]{6}$/.test(s)) return null;
        return [
            parseInt(s.slice(0, 2), 16),
            parseInt(s.slice(2, 4), 16),
            parseInt(s.slice(4, 6), 16)
        ];
    }

    function colorDist(a, b) {
        var dr = a[0] - b[0], dg = a[1] - b[1], db = a[2] - b[2];
        return Math.sqrt(dr * dr + dg * dg + db * db);
    }

    function enhance($) {
        if (!$ || !$.fn || typeof $.fn.select2 === 'undefined') return;
        var $sel = $('#id_active_color');
        if (!$sel.length) return;

        var currentTerm = '';

        function tpl(state) {
            if (!state.id) return state.text;
            var el = state.element;
            var color = el ? el.getAttribute('data-color') : null;
            var texture = el ? el.getAttribute('data-texture') : null;
            var $row = $('<span class="color-opt"></span>');
            var $sw = $('<span class="color-opt__swatch"></span>');
            if (texture) {
                $sw.css('background-image', 'url("' + texture + '")');
            } else if (color) {
                $sw.css('background-color', color);
            } else {
                $sw.addClass('is-empty');
            }
            $row.append($sw).append($('<span class="color-opt__label"></span>').text(state.text));
            return $row;
        }

        function matcher(params, data) {
            var term = (params.term || '').trim();
            currentTerm = term;
            if (term === '') return data;

            var hex = parseHex(term);
            if (hex) {
                // HEX-пошук: лишаємо лише кольорові опції (текстури/порожнє — пропускаємо)
                var rgb = parseHex(data.element && data.element.getAttribute('data-color'));
                return rgb ? data : null;
            }

            // Звичайний пошук за назвою кольору
            if (data.text && data.text.toLowerCase().indexOf(term.toLowerCase()) > -1) {
                return data;
            }
            return null;
        }

        function sorter(data) {
            var hex = parseHex(currentTerm);
            if (!hex || !data) return data;
            return data.slice().sort(function (a, b) {
                var ra = parseHex(a.element && a.element.getAttribute('data-color'));
                var rb = parseHex(b.element && b.element.getAttribute('data-color'));
                var da = ra ? colorDist(hex, ra) : Infinity;
                var db = rb ? colorDist(hex, rb) : Infinity;
                return da - db;
            });
        }

        if ($sel.hasClass('select2-hidden-accessible')) {
            try { $sel.select2('destroy'); } catch (e) { /* ignore */ }
        }
        $sel.select2({
            theme: 'admin-autocomplete',  // тема Django → коректні кольори у світлій/темній адмінці
            templateResult: tpl,
            templateSelection: tpl,
            matcher: matcher,
            sorter: sorter,
            width: 'resolve'
        });
    }

    function boot() {
        if (window.django && window.django.jQuery) {
            window.django.jQuery(function () { enhance(window.django.jQuery); });
        } else if (window.jQuery) {
            window.jQuery(function () { enhance(window.jQuery); });
        }
    }

    boot();
})();
