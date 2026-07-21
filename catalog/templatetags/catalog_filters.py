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

#: Prepositions a category name can start with. When it does, the noun goes
#: in front — "Килими в дитячу", not "В дитячу килими".
_PREPOSITIONS = ("в ", "у ", "для ", "під ", "на ", "до ", "з ")


@register.filter
def category_phrase(title):
    """
    Turn a category name into something someone would actually type.

    Category titles are stored the way they read in a menu — "Українські",
    "В дитячу" — where the surrounding page supplies the noun. A <title> has
    no surrounding page, so "Українські | mr.Carpet" told Google the page was
    about something Ukrainian without ever saying what. It could not rank for
    "українські килими" because the word was not there.

    Three shapes, all present in the real data:

    * "Акрилові килими" — already complete, left alone
    * "В дитячу"        — preposition first, so the noun leads
    * "Українські"      — adjective, so the noun follows
    """
    text = (title or "").strip()
    if not text:
        return ""

    lowered = text.lower()
    if "килим" in lowered:
        return text
    if lowered.startswith(_PREPOSITIONS):
        return f"Килими {lowered}"
    return f"{text} килими"


@register.filter
def category_meta_description(categorie):
    """
    Fallback description for a category page.

    Leads with the phrase people search for rather than with the shop name:
    Google truncates around 160 characters and the first words are what a
    reader scans.
    """
    phrase = category_phrase(getattr(categorie, "title", ""))
    if not phrase:
        return "Килими mr.Carpet. Доставка по Україні."
    return (
        f"{phrase} — купити в інтернет-магазині mr.Carpet. "
        f"Українські та турецькі виробники, доставка по всій Україні."
    )
