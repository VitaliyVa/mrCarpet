"""Custom admin form widgets shared across the catalog admin."""

from django import forms
from django.contrib.admin.widgets import AdminFileWidget
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from catalog.models import ProductColor


class ColorSelectWidget(forms.Select):
    """
    Select для «Активного кольору»: додає кожній опції data-color / data-texture,
    щоб JS (select2) намалював кружечок-прев'ю кольору або текстури.
    Якщо select2 недоступний — лишається звичайний робочий select.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        css = (self.attrs.get('class', '') + ' color-select').strip()
        self.attrs['class'] = css

    def _color_map(self):
        cmap = getattr(self, '_cmap', None)
        if cmap is None:
            cmap = {}
            for c in ProductColor.objects.all():
                cmap[str(c.pk)] = {
                    'color': str(c.color) if c.color else '',
                    'texture': c.texture.url if c.texture else '',
                }
            self._cmap = cmap
        return cmap

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        pk = str(getattr(value, 'value', value) or '')
        data = self._color_map().get(pk)
        if data:
            if data['texture']:
                option['attrs']['data-texture'] = data['texture']
            elif data['color']:
                option['attrs']['data-color'] = data['color']
        return option


class ImagePreviewWidget(AdminFileWidget):
    """Віджет ImageField, що показує мініатюру завантаженого фото біля поля."""

    def render(self, name, value, attrs=None, renderer=None):
        html = super().render(name, value, attrs, renderer)
        # value — це FieldFile; порожній FieldFile дає False, тож прев'ю лише коли є файл
        if value and getattr(value, "url", None):
            preview = format_html(
                '<div class="image-preview" style="margin:0 0 8px;">'
                '<img src="{}" alt="preview" style="max-height:160px; max-width:240px; '
                'border-radius:8px; border:1px solid var(--border-color,#ccc); '
                'object-fit:contain; background:#fff; padding:2px;" /></div>',
                value.url,
            )
            return mark_safe(preview + html)
        return html
