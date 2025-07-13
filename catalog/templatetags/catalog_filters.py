from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Отримує значення з словника за ключем"""
    if isinstance(dictionary, dict):
        return dictionary.get(key, [])
    return []


@register.filter
def is_in_list(value, list_str):
    """Перевіряє чи значення є в списку (як рядок)"""
    if not list_str:
        return False
    if isinstance(list_str, str):
        return value in list_str.split(',')
    return value in list_str


@register.filter
def getlist(querydict, key):
    """Отримує список значень з QueryDict за ключем"""
    if hasattr(querydict, 'getlist'):
        return querydict.getlist(key)
    return [] 