from django import forms
from .models import ProductColor


class ProductColorAdminForm(forms.ModelForm):
    """Custom form для ProductColor admin з полем для пошуку товарів"""
    product_name_search = forms.CharField(
        label="Назва товару для пошуку",
        required=False,
        help_text="Введіть назву товару для пошуку та оновлення кольорів",
        widget=forms.TextInput(attrs={
            'class': 'vTextField',
            'placeholder': 'Введіть назву товару...'
        })
    )

    class Meta:
        model = ProductColor
        fields = ['title', 'color']
