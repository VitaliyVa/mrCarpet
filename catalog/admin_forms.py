"""Admin ModelForms for Product — business rules beyond model blank=True."""

from __future__ import annotations

from django import forms

from catalog.models import Product, ProductAttribute

DEFAULT_CATALOG_IMAGE = "products/default.png"
MSG_REQUIRED = "Це поле обов'язкове."
MSG_NEED_IMAGE = "Завантажте каталожне зображення."
MSG_NEED_CATEGORY = "Оберіть хоча б одну категорію."
MSG_NEED_CUSTOM_PRICE = "Це поле обов'язкове для кастомної варіації."


def file_field_name(value) -> str:
    """Normalize ImageField/FileField cleaned value to a storage path."""
    if value is None or value is False:
        return ""
    if isinstance(value, str):
        return value
    return getattr(value, "name", "") or ""


def is_default_catalog_image(value) -> bool:
    return file_field_name(value) == DEFAULT_CATALOG_IMAGE


class ProductAdminForm(forms.ModelForm):
    """
    Model fields are mostly blank=True, but a sellable product needs more
    than a title (storefront uses variations for price/size; ProductManager
    hides products with no quantity).
    """

    # Не модельне поле: разове рішення для конкретного створення.
    # Показуємо ЛИШЕ на формі створення — при редагуванні постинг
    # неможливий у принципі (сигнал реагує тільки на created=True).
    post_to_socials = forms.BooleanField(
        label="Опублікувати в соцмережах",
        required=False,
        initial=True,
        help_text=(
            "Після збереження новий товар автоматично піде в Telegram, "
            "Instagram/Facebook і Viber (ті, що увімкнені в Social settings). "
            "Зніміть галочку, щоб додати товар тихо. "
            "Під час редагування товару пост не повторюється."
        ),
    )

    class Meta:
        model = Product
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Редагування наявного товару — галочка не потрібна
        if self.instance and self.instance.pk:
            self.fields.pop("post_to_socials", None)

    def clean_title(self):
        title = (self.cleaned_data.get("title") or "").strip()
        if not title:
            raise forms.ValidationError(MSG_REQUIRED)
        return title

    def clean_image(self):
        image = self.cleaned_data.get("image")
        # ClearableFileInput: False → user checked "clear"
        if image is False:
            raise forms.ValidationError(MSG_NEED_IMAGE)

        if image:
            # On add, model default often arrives as plain path string
            if is_default_catalog_image(image) or not file_field_name(image):
                raise forms.ValidationError(MSG_NEED_IMAGE)
            return image

        if self.instance.pk and self.instance.image:
            if not is_default_catalog_image(self.instance.image):
                return self.instance.image

        raise forms.ValidationError(MSG_NEED_IMAGE)

    def clean(self):
        cleaned = super().clean()
        categories = cleaned.get("categories")
        if categories is not None and len(categories) == 0:
            self.add_error("categories", MSG_NEED_CATEGORY)
        return cleaned


class ProductAttributeAdminForm(forms.ModelForm):
    """Fixed row: size + price + quantity. Custom row: custom_price + quantity."""

    class Meta:
        model = ProductAttribute
        exclude = ("sort_order",)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("DELETE"):
            return cleaned

        custom = bool(cleaned.get("custom_attribute"))
        size = cleaned.get("size")
        price = cleaned.get("price")
        quantity = cleaned.get("quantity")
        custom_price = cleaned.get("custom_price")
        widths = cleaned.get("width")

        has_widths = bool(widths)
        has_any = any(
            [
                size,
                price is not None,
                quantity is not None,
                custom,
                custom_price is not None,
                cleaned.get("discount") is not None,
                cleaned.get("min_len") is not None,
                cleaned.get("max_len") is not None,
                has_widths,
            ]
        )
        if not has_any:
            return cleaned

        if quantity is None:
            self.add_error("quantity", MSG_REQUIRED)

        if custom:
            if custom_price is None:
                self.add_error("custom_price", MSG_NEED_CUSTOM_PRICE)
        else:
            if not size:
                self.add_error("size", MSG_REQUIRED)
            if price is None:
                self.add_error("price", MSG_REQUIRED)

        return cleaned
