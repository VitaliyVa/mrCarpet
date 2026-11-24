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
        f"{phrase}: купити в інтернет-магазині mr.Carpet. "
        f"Українські та турецькі виробники, доставка по всій Україні."
    )


@register.filter
def ga_item_id(attr):
    """GA4 item_id of a ProductAttribute = Merchant feed g:id (merchant_feed.offer_id)."""
    from project.merchant_feed import offer_id

    if attr is None:
        return ""
    return offer_id(attr.product_id, attr)


@register.filter
def size_cm(size):
    """Size label as the Merchant feed and the ads write it: "2.0х3.0" ->
    "200x300 см" (project.merchant_feed.format_size). Display only: chips
    keep the stored label, JS and the AR viewer read it."""
    from project.merchant_feed import format_size

    if size is None:
        return ""
    if not isinstance(size, str):
        size = getattr(size, "title", "") or ""
    return format_size(str(size))


def plural_uk_form(n, forms):
    """
    Ukrainian plural: 1 товар, 2-4 товари, 5+ товарів, 11-14 товарів.

    `forms` is "one,few,many" ("товар,товари,товарів") or a 3-item sequence.
    """
    if isinstance(forms, str):
        forms = [f.strip() for f in forms.split(",")]
    one, few, many = forms
    try:
        n = abs(int(n))
    except (TypeError, ValueError):
        return many
    if 11 <= n % 100 <= 14:
        return many
    last = n % 10
    if last == 1:
        return one
    if 2 <= last <= 4:
        return few
    return many


@register.filter
def plural_uk(n, forms):
    """{{ count }} {{ count|plural_uk:"товар,товари,товарів" }}"""
    return plural_uk_form(n, forms)
