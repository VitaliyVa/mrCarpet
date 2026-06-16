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
                'Вставлено з буфера: ' + file.name + '</div>';
        };
        reader.readAsDataURL(file);
    }

    function onPaste(e) {
        var input = document.getElementById(INPUT_ID);
        if (!input) return;
        var blob = getImageBlob(e.clipboardData || window.clipboardData);
        if (!blob) return;

        e.preventDefault();
        var ext = (blob.type.split('/')[1] || 'png').split('+')[0];
        var file = new File([blob], 'texture-' + Date.now() + '.' + ext, { type: blob.type });
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

    function init() {
        var input = document.getElementById(INPUT_ID);
        if (!input) return;
        document.addEventListener('paste', onPaste);
        if (!document.getElementById('texture-paste-hint')) {
            var hint = document.createElement('div');
            hint.id = 'texture-paste-hint';
            hint.style.cssText = 'font-size:.85em; color:var(--body-quiet-color,#888); margin-top:4px;';
            hint.textContent = 'Підказка: можна вставити зображення з буфера обміну — Ctrl+V';
            input.parentNode.appendChild(hint);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
