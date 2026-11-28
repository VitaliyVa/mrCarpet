import re

import django_filters
from django.db.models import Min, Q, Case, When, ExpressionWrapper, F, FloatField
from django.db.models.functions import Coalesce

from .models import Product, ProductSpecification, Specification


class ProductFilter(django_filters.FilterSet):
    size = django_filters.CharFilter(method="filter_by_size")
    price = django_filters.OrderingFilter(
        fields=("product_attr__price",), method="order_by_price"
    )
    title = django_filters.OrderingFilter(fields=("title",))
    color = django_filters.CharFilter(
        field_name="product_specs__spec_value__title", method="filter_by_color"
    )
    q = django_filters.CharFilter(method="search", label="Search query")

    class Meta:
        model = Product
        fields = ["size", "price"]

    def filter_by_size(self, queryset, name, value):
        # `size` is a ProductSize id. A bot or a broken link sending text
        # (?size=60x100) used to raise ValueError deep in the ORM and 500
        # the whole listing; a non-id simply matches nothing now.
        value = (value or "").strip()
        if not value.isdigit():
            return queryset.none()
        return queryset.filter(product_attr__size=int(value))

    def filter_queryset(self, queryset):
        """
        Перевизначаємо filter_queryset для обробки динамічних фільтрів специфікацій
        """
        # Спочатку застосовуємо стандартні фільтри
        queryset = super().filter_queryset(queryset)
        
        # Фільтрація по діапазону цін (price_min, price_max)
        price_min = self.data.get('price_min')
        price_max = self.data.get('price_max')
        
        if price_min or price_max:
            # Анотуємо effective_price_attr для кожної варіації: кастомна -> custom_price, інша -> ціна з урахуванням знижки (або без)
            effective_price_expr = Case(
                When(
                    product_attr__custom_attribute=True,
                    then=F('product_attr__custom_price')
                ),
                default=ExpressionWrapper(
                    F('product_attr__price') * (1 - Coalesce(F('product_attr__discount'), 0) / 100.0),
                    output_field=FloatField()
                ),
                output_field=FloatField()
            )

            queryset = queryset.annotate(
                effective_price_attr=effective_price_expr
            ).annotate(
                effective_price=Min('effective_price_attr')
            )
            
            if price_min:
                try:
                    price_min_value = float(price_min)
                    queryset = queryset.filter(effective_price__gte=price_min_value)
                except (ValueError, TypeError):
                    pass
            
            if price_max:
                try:
                    price_max_value = float(price_max)
                    queryset = queryset.filter(effective_price__lte=price_max_value)
                except (ValueError, TypeError):
                    pass
        
        # Обробляємо динамічні фільтри для специфікацій
        # Отримуємо всі назви специфікацій
        all_specs = Specification.objects.values_list('title', flat=True)

        # Перевіряємо всі GET параметри (унікальні ключі)
        for key in self.data.keys():
            # Пропускаємо price_min/price_max (вже оброблено вище)
            if key in ['price_min', 'price_max']:
                continue

            # Перевіряємо чи це специфікація (назва в нижньому регістрі)
            spec_name_lower = key.lower()
            spec_name_matches = [spec for spec in all_specs if spec.lower() == spec_name_lower]

            if not spec_name_matches:
                continue

            # Підтримка вибору кількох значень (чекбокси): беремо ВСІ значення ключа
            if hasattr(self.data, 'getlist'):
                values = [v for v in self.data.getlist(key) if v]
            else:
                value = self.data.get(key)
                values = [value] if value else []

            if values:
                # Знайшли специфікацію, фільтруємо по ній (OR в межах однієї спеки)
                spec_name = spec_name_matches[0]
                specs = ProductSpecification.objects.filter(
                    specification__title=spec_name,
                    spec_value__title__in=values
                )
                queryset = queryset.filter(product_specs__in=specs).distinct()

        return queryset

    def order_by_price(self, queryset, name, value):
        effective_price_expr = Case(
            When(
                product_attr__custom_attribute=True,
                then=F('product_attr__custom_price')
            ),
            default=ExpressionWrapper(
                F('product_attr__price') * (1 - Coalesce(F('product_attr__discount'), 0) / 100.0),
                output_field=FloatField()
            ),
            output_field=FloatField()
        )

        queryset = queryset.annotate(
            effective_price_attr=effective_price_expr
        ).annotate(min_effective_price=Min('effective_price_attr'))

        sort_value = value[0] if value else 'min_effective_price'
        if sort_value.startswith('-'):
            return queryset.order_by('-min_effective_price').distinct()
        return queryset.order_by('min_effective_price').distinct()

    def filter_by_color(self, queryset, name, value):
        specs = ProductSpecification.objects.filter(
            specification__title="Колір", spec_value__title=value
        )
        return queryset.filter(product_specs__in=specs)

    def search(self, queryset, name, value):
        """
        Every meaningful word of the query must match somewhere: title,
        description, colour, a specification value, a category or a size.
        "сірий 200x300" used to look for that whole phrase in the title and
        found nothing. Word endings are trimmed (сірий / сіра / сірі),
        sizes in cm are read as the shop's metres (200x300 -> 2.0х3.0).
        """
        tokens = search_tokens(value)
        if not tokens:
            return queryset
        for token in tokens:
            queryset = queryset.filter(token_q(token))
        return queryset.distinct()


SEARCH_STOP_WORDS = {
    "купити", "куплю", "ціна", "ціни", "ціною", "недорого", "дешево", "дешеві",
    "інтернет", "магазин", "магазині", "україна", "україні", "доставка",
    "для", "під", "та", "або", "на", "в", "у", "з", "із", "і", "й",
    "см", "м",
}

_SIZE_RE = re.compile(r"^(\d+(?:[.,]\d+)?)\s*[xх×*]\s*(\d+(?:[.,]\d+)?)$", re.I)


def _metres(raw: str) -> float:
    number = float(raw.replace(",", "."))
    return number / 100 if number > 10 else number


def _fmt_metres(number: float) -> str:
    text = f"{number:.2f}".rstrip("0")
    return text + "0" if text.endswith(".") else text


def size_variants(token: str) -> list[str]:
    """'200x300', '2х3', '2.0x3.0' -> ['2.0х3.0', '2.0x3.0']."""
    match = _SIZE_RE.match(token)
    if not match:
        return []
    width, length = (_fmt_metres(_metres(part)) for part in match.groups())
    return [f"{width}х{length}", f"{width}x{length}"]


def search_tokens(value: str) -> list[str]:
    text = re.sub(r"(\d)\s*([xх×*])\s*(\d)", r"\1\2\3", (value or "").strip().lower())
    tokens = []
    for word in re.split(r"[\s,;/]+", text):
        word = word.strip(".!?\"'«»()")
        if not word or word in SEARCH_STOP_WORDS:
            continue
        if size_variants(word):
            tokens.append(word)
        elif len(word) >= 2:
            tokens.append(word)
    return tokens


def _stem(word: str) -> str:
    # Crude Ukrainian ending trim: сірий/сіра/сірі -> сір, овальний -> оваль.
    if len(word) >= 5:
        return word[:-2]
    if len(word) == 4:
        return word[:-1]
    return word


def token_q(token: str) -> Q:
    sizes = size_variants(token)
    if sizes:
        q = Q()
        for size in sizes:
            q |= Q(product_attr__size__title__iexact=size)
        return q
    stem = _stem(token)
    q = Q(product_attr__size__title__icontains=token)
    # SQLite's LIKE ignores case only for ASCII, so "кил" would miss "Килим":
    # try the lower and the capitalised form of the stem.
    for form in {stem, stem.capitalize()}:
        q |= (
            Q(title__icontains=form)
            | Q(description__icontains=form)
            | Q(colors__title__icontains=form)
            | Q(product_specs__spec_value__title__icontains=form)
            | Q(categories__title__icontains=form)
        )
    return q
