'use strict';
/*
 * Вставка зображення текстури з буфера обміну (Ctrl+V) у формі кольору адмінки.
 * Працює, коли в буфері саме ДАНІ зображення (скріншот, «копіювати зображення»).
 * Бере зображення з clipboard → кладе у файловий інпут #id_texture через DataTransfer
 * → показує прев'ю. Якщо браузер не дає зображення з буфера — нічого не ламається.
 */
(function () {
    var INPUT_ID = 'id_texture';

    function getImageBlob(clipboardData) {
        if (!clipboardData || !clipboardData.items) return null;
        for (var i = 0; i < clipboardData.items.length; i++) {
            var item = clipboardData.items[i];
            if (item.kind === 'file' && item.type.indexOf('image/') === 0) {
                return item.getAsFile();
            }
        }
        return null;
    }

    function showPreview(input, file) {
        var id = 'texture-paste-preview';
        var box = document.getElementById(id);
        if (!box) {
            box = document.createElement('div');
            box.id = id;
            box.style.cssText = 'margin-top:8px;';
            input.parentNode.appendChild(box);
        }
        var reader = new FileReader();
        reader.onload = function (ev) {
            box.innerHTML =
                '<img alt="preview" src="' + ev.target.result + '" ' +
                'style="max-height:140px; max-width:200px; border-radius:8px; ' +
                'border:1px solid var(--border-color,#ccc); object-fit:contain; ' +
                'background:#fff; padding:2px;" />' +
                '<div style="font-size:.85em; color:var(--body-quiet-color,#888); margin-top:4px;">' +
                'Оброблено: 40×40, ' + (file.type.indexOf('webp') > -1 ? 'WebP' : file.type) + '</div>';
        };
        reader.readAsDataURL(file);
    }

    var SIZE = 40; // авто-обрізка вставленої текстури до 40×40 (квадрат по центру)

    function cropToSquare(blob, size, cb) {
        var url = URL.createObjectURL(blob);
        var img = new Image();
        img.onload = function () {
            try {
                var canvas = document.createElement('canvas');
                canvas.width = size;
                canvas.height = size;
                var ctx = canvas.getContext('2d');
                // cover: беремо центральний квадрат і масштабуємо до size×size без спотворення
                var s = Math.min(img.naturalWidth, img.naturalHeight);
                var sx = (img.naturalWidth - s) / 2;
                var sy = (img.naturalHeight - s) / 2;
                ctx.drawImage(img, sx, sy, s, s, 0, 0, size, size);
                // конвертація у WebP; якщо браузер не вміє кодувати webp (out=null) —
                // відкочуємось на PNG, але зберігаємо обрізку 40×40
                canvas.toBlob(function (out) {
                    if (out) {
                        URL.revokeObjectURL(url);
                        cb(out);
                        return;
                    }
                    canvas.toBlob(function (pngOut) {
                        URL.revokeObjectURL(url);
                        cb(pngOut);
                    }, 'image/png');
                }, 'image/webp', 0.92);
            } catch (err) {
                URL.revokeObjectURL(url);
                cb(null);
            }
        };
        img.onerror = function () { URL.revokeObjectURL(url); cb(null); };
        img.src = url;
    }

    function putFile(input, blob) {
        var type = blob.type || 'image/png';
        var ext = type.indexOf('webp') > -1 ? 'webp'
            : (type.indexOf('jpeg') > -1 || type.indexOf('jpg') > -1) ? 'jpg' : 'png';
        var file = new File([blob], 'texture-' + Date.now() + '.' + ext, { type: type });
        try {
            var dt = new DataTransfer();
            dt.items.add(file);
            input.files = dt.files;
            input.dispatchEvent(new Event('change', { bubbles: true }));
            showPreview(input, file);
        } catch (err) {
            console.error('Не вдалося вставити текстуру з буфера:', err);
        }
    }

    function onPaste(e) {
        var input = document.getElementById(INPUT_ID);
        if (!input) return;
        var blob = getImageBlob(e.clipboardData || window.clipboardData);
        if (!blob) return;

        e.preventDefault();
        cropToSquare(blob, SIZE, function (out) {
            putFile(input, out || blob); // якщо обрізка не вдалась — кладемо оригінал
        });
    }

    function init() {
        var input = document.getElementById(INPUT_ID);
        if (!input) return;
        document.addEventListener('paste', onPaste);
        if (!document.getElementById('texture-paste-hint')) {
            var hint = document.createElement('div');
            hint.id = 'texture-paste-hint';
            hint.style.cssText = 'font-size:.85em; color:var(--body-quiet-color,#888); margin-top:4px;';
            hint.textContent = 'Підказка: Ctrl+V вставляє зображення з буфера (авто-обрізка до 40×40 + WebP)';
            input.parentNode.appendChild(hint);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
