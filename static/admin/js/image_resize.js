'use strict';
/*
 * Авто-обробка зображень товару в адмінці при виборі/зміні файлу:
 *   - Product.image / Product.hover_image  → ширина до 300px (висота пропорційно)
 *   - ProductImage (інлайн «Зображення продуктів»), name=images-N-image → ширина до 800px
 *   - усе конвертується у WebP (з фолбеком на PNG, якщо браузер не вміє webp).
 * Пропорції зберігаються (без обрізки). Якщо зображення вже вужче за ціль — не збільшуємо,
 * лише конвертуємо у WebP. Делегований обробник ловить і динамічно додані інлайн-рядки.
 */
(function () {
    var RULES = [
        { test: function (n) { return n === 'image' || n === 'hover_image'; }, maxWidth: 300 },
        { test: function (n) { return /^images-\d+-image$/.test(n); }, maxWidth: 800 }
    ];
    var selfUpdate = false; // ми самі міняємо input.files (захист від можливого зациклення)

    function ruleFor(input) {
        var name = input && input.name;
        if (!name) return null;
        for (var i = 0; i < RULES.length; i++) {
            if (RULES[i].test(name)) return RULES[i];
        }
        return null;
    }

    function resizeByWidth(blob, maxWidth, cb) {
        var url = URL.createObjectURL(blob);
        var img = new Image();
        img.onload = function () {
            try {
                var w = img.naturalWidth, h = img.naturalHeight;
                if (!w || !h) { URL.revokeObjectURL(url); cb(null); return; }
                var tw = w, th = h;
                if (w > maxWidth) {
                    tw = maxWidth;
                    th = Math.max(1, Math.round(h * (maxWidth / w)));
                }
                var canvas = document.createElement('canvas');
                canvas.width = tw;
                canvas.height = th;
                canvas.getContext('2d').drawImage(img, 0, 0, tw, th);
                canvas.toBlob(function (out) {
                    if (out) { URL.revokeObjectURL(url); cb(out); return; }
                    canvas.toBlob(function (p) { URL.revokeObjectURL(url); cb(p); }, 'image/png');
                }, 'image/webp', 0.9);
            } catch (e) {
                URL.revokeObjectURL(url);
                cb(null);
            }
        };
        img.onerror = function () { URL.revokeObjectURL(url); cb(null); };
        img.src = url;
    }

    function extFor(type) {
        if (type.indexOf('webp') > -1) return 'webp';
        if (type.indexOf('jpeg') > -1 || type.indexOf('jpg') > -1) return 'jpg';
        return 'png';
    }

    function showPreview(input, file, w) {
        var box = input.parentNode.querySelector('.img-resize-preview');
        if (!box) {
            box = document.createElement('div');
            box.className = 'img-resize-preview';
            box.style.cssText = 'margin-top:6px;';
            input.parentNode.appendChild(box);
        }
        var reader = new FileReader();
        reader.onload = function (ev) {
            box.innerHTML =
                '<img alt="preview" src="' + ev.target.result + '" ' +
                'style="max-height:90px; max-width:160px; border-radius:6px; ' +
                'border:1px solid var(--border-color,#ccc); object-fit:contain; ' +
                'background:#fff; padding:2px;" />' +
                '<div style="font-size:.8em; color:var(--body-quiet-color,#888); margin-top:3px;">' +
                'Оброблено: до ' + w + 'px, ' + (file.type.indexOf('webp') > -1 ? 'WebP' : file.type) + '</div>';
        };
        reader.readAsDataURL(file);
    }

    function setFile(input, blob, maxWidth) {
        var type = blob.type || 'image/png';
        var base = input.name.indexOf('hover') > -1 ? 'hover' : 'product';
        var file = new File([blob], base + '-' + Date.now() + '.' + extFor(type), { type: type });
        try {
            var dt = new DataTransfer();
            dt.items.add(file);
            selfUpdate = true;
            input.files = dt.files;
            selfUpdate = false;
            showPreview(input, file, maxWidth);
        } catch (err) {
            selfUpdate = false;
            console.error('Не вдалося обробити зображення:', err);
        }
    }

    function onChange(e) {
        if (selfUpdate) return;
        var input = e.target;
        if (!input || input.type !== 'file') return;
        var rule = ruleFor(input);
        if (!rule) return;
        if (!input.files || !input.files.length) return;
        var file = input.files[0];
        if (!file.type || file.type.indexOf('image/') !== 0) return; // не зображення — не чіпаємо
        resizeByWidth(file, rule.maxWidth, function (out) {
            if (!out) return; // не вдалось — лишаємо оригінал як є
            setFile(input, out, rule.maxWidth);
        });
    }

    // change спливає → один делегований обробник ловить і головні поля, і інлайн (зокрема нові рядки)
    document.addEventListener('change', onChange);
})();
