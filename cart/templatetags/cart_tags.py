from django import template
from enum import StrEnum

register = template.Library()


@register.simple_tag()
def get_quantity_title(quantity: str) -> str:
    quantity = int(quantity)
    if quantity == 1:
        return 'товар'
    elif 2 <= quantity <= 4:
        return 'товара'
    else:
        return 'товарів'

