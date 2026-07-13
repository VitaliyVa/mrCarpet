'use strict';

(function () {
    var GROUP_ID = 'images-group';
    var ORDER_STEP = 10;

    function getGroup() {
        return document.getElementById(GROUP_ID);
    }

    function getSortableRows(group) {
        return Array.prototype.slice.call(
            group.querySelectorAll('tbody tr.form-row:not(.empty-form)')
        );
    }

    function getOrderInput(row) {
        return row.querySelector('input[name$="-sort_order"]');
    }

    function renumberSortOrders(group) {
        var rows = getSortableRows(group);
        rows.forEach(function (row, index) {
            var input = getOrderInput(row);
            if (input) input.value = (index + 1) * ORDER_STEP;
        });
    }

    function injectDragColumn(group) {
        if (group.dataset.sortableReady) return;
        group.dataset.sortableReady = '1';

        var theadRow = group.querySelector('thead tr');
        if (theadRow) {
            var th = document.createElement('th');
            th.className = 'product-image-drag-col';
            th.textContent = '↕';
            th.title = 'Перетягніть рядок, щоб змінити порядок';
            theadRow.insertBefore(th, theadRow.firstChild);
        }

        getSortableRows(group).forEach(function (row) {
            attachRowDrag(group, row);
        });
    }

    function createDragCell() {
        var td = document.createElement('td');
        td.className = 'product-image-drag-col';
        var handle = document.createElement('span');
        handle.className = 'product-image-drag-handle';
        handle.setAttribute('draggable', 'true');
        handle.title = 'Перетягніть для зміни порядка';
        handle.textContent = '⋮⋮';
        td.appendChild(handle);
        return td;
    }

    function attachRowDrag(group, row) {
        if (row.dataset.dragReady) return;
        row.dataset.dragReady = '1';

        var dragCell = createDragCell();
        row.insertBefore(dragCell, row.firstChild);
        var handle = dragCell.querySelector('.product-image-drag-handle');

        handle.addEventListener('dragstart', function (e) {
            row.classList.add('is-dragging');
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', row.rowIndex);
        });

        handle.addEventListener('dragend', function () {
            row.classList.remove('is-dragging');
            group.querySelectorAll('.is-drag-over').forEach(function (el) {
                el.classList.remove('is-drag-over');
            });
        });

        row.addEventListener('dragover', function (e) {
            if (group.querySelector('.is-dragging') === row) return;
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            row.classList.add('is-drag-over');
        });

        row.addEventListener('dragleave', function () {
            row.classList.remove('is-drag-over');
        });

        row.addEventListener('drop', function (e) {
            e.preventDefault();
            row.classList.remove('is-drag-over');
            var dragging = group.querySelector('tbody tr.is-dragging');
            if (!dragging || dragging === row) return;

            var tbody = row.parentNode;
            var rows = getSortableRows(group);
            var dragIndex = rows.indexOf(dragging);
            var dropIndex = rows.indexOf(row);
            if (dragIndex < 0 || dropIndex < 0) return;

            if (dragIndex < dropIndex) {
                tbody.insertBefore(dragging, row.nextSibling);
            } else {
                tbody.insertBefore(dragging, row);
            }
            renumberSortOrders(group);
        });
    }

    function observeInlineRows(group) {
        var tbody = group.querySelector('tbody');
        if (!tbody || group.dataset.observerReady) return;
        group.dataset.observerReady = '1';

        var observer = new MutationObserver(function () {
            getSortableRows(group).forEach(function (row) {
                attachRowDrag(group, row);
            });
        });
        observer.observe(tbody, { childList: true, subtree: true });
    }

    function init() {
        var group = getGroup();
        if (!group) return;
        injectDragColumn(group);
        observeInlineRows(group);
    }

    document.addEventListener('DOMContentLoaded', init);
})();
