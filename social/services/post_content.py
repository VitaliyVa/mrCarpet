"""Спільний контент товарних постів — один source of truth для TG/Viber/IG/FB.

Структура поста (емоджі — функціональні маркери блоків, не декор):

    ✨ Назва товару

    🏷 Розміри та ціни:
    • 0.8х1.5 — 1000 грн
    • 1.2х1.8 — 1800 грн · немає
    📏 Індивідуальний розмір — від 500 грн/м²

    🧵 Характеристики:
    • Матеріал: поліпропілен
    • Форма: прямокутна

    👉 Детальніше та замовлення:
    https://mrcarpet24.com/...

    Питання? Пишіть — підкажемо 💬

Ліміти платформ різні (Viber picture 768, TG caption 1024, IG 2200),
тому рендер ступенево жертвує блоками: спершу підрізає характеристики,
потім розміри (з рядком «…і ще N розмірів на сайті»), потім дружній
фінал. Назва і лінк — недоторкані.
"""

from __future__ import annotations

import html as html_mod
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# (specs_limit, sizes_limit, friendly_outro) — від повного до мінімального
_TRIM_STAGES = (
    (None, None, True),
    (5, 6, True),
    (3, 4, False),
    (0, 3, False),
)

FRIENDLY_OUTRO = "Питання? Пишіть — підкажемо 💬"
CTA_TEXT = "Детальніше та замовлення"


@dataclass
class ProductPostContent:
    title: str
    url: str
    size_lines: list[str] = field(default_factory=list)
    custom_size_line: str = ""
    price_line: str = ""
    spec_lines: list[str] = field(default_factory=list)
    ar_available: bool = False


def build_product_content(product) -> ProductPostContent:
    from project.telegram_utils import product_absolute_url

    title = (product.title or "Товар").strip()
    try:
        url = product_absolute_url(product)
    except Exception:
        url = ""

    content = ProductPostContent(title=title, url=url)

    # Фіксовані розміри з цінами; відсутні — з поміткою (як у каталозі)
    try:
        attrs = list(
            product.get_size_attrs()
            .select_related("size")
            .order_by("sort_order", "id")
        )
    except Exception:
        attrs = []
    for attr in attrs:
        try:
            size_title = (attr.size.title if attr.size_id else "") or ""
        except Exception:
            size_title = ""
        size_title = size_title.strip() or "розмір"
        try:
            price = attr.get_total_price()
        except Exception:
            price = attr.price
        price_s = f"{price} грн" if price is not None else "—"
        stock = "" if getattr(attr, "in_stock", True) else " · немає"
        content.size_lines.append(f"{size_title} — {price_s}{stock}")

    # Килим під замовлення (ціна за м²) — сильний selling point
    try:
        custom = product.product_attr.filter(custom_attribute=True).first()
        if custom and custom.custom_price:
            content.custom_size_line = (
                f"Індивідуальний розмір — від {custom.custom_price} грн/м²"
            )
    except Exception:
        pass

    # Fallback-ціна, якщо немає ні розмірів, ні кастому
    if not content.size_lines and not content.custom_size_line:
        try:
            attr = product.get_default_size_attr()
            if attr is not None and not getattr(attr, "custom_attribute", False):
                content.price_line = f"{attr.get_total_price()} грн"
        except Exception:
            pass

    # Характеристики: "Назва: Значення"
    try:
        specs = product.product_specs.select_related(
            "specification", "spec_value"
        ).order_by("id")
        for spec in specs:
            name = (getattr(spec.specification, "title", "") or "").strip()
            value = (getattr(spec.spec_value, "title", "") or "").strip()
            if name and value:
                content.spec_lines.append(f"{name}: {value}")
    except Exception:
        pass

    # 3D/AR-примірка готова → заохочення в пості (TG/IG/FB; Viber скіпає)
    try:
        content.ar_available = (
            getattr(product, "ar_status", "") == "ready"
            and bool(getattr(product, "ar_texture", None))
        )
    except Exception:
        pass

    return content


AR_TEASER = (
    "📲 Приміряйте цей килим у себе вдома: на сторінці товару "
    "натисніть «Дивитись у 3D»"
)


def _rows(
    content: ProductPostContent,
    *,
    specs_limit,
    sizes_limit,
    friendly: bool,
    with_url: bool,
    include_ar: bool = True,
    allow_friendly_outro: bool = True,
) -> list[tuple[str, str]]:
    """Рядки поста як пари (plain, telegram_html)."""
    esc = html_mod.escape
    rows: list[tuple[str, str]] = []

    rows.append((f"✨ {content.title}", f"✨ <b>{esc(content.title)}</b>"))

    size_lines = content.size_lines
    hidden = 0
    if sizes_limit is not None and len(size_lines) > sizes_limit:
        hidden = len(size_lines) - sizes_limit
        size_lines = size_lines[:sizes_limit]
    if size_lines or content.custom_size_line or content.price_line:
        rows.append(("", ""))
        if size_lines:
            rows.append(("🏷 Розміри та ціни:", "🏷 Розміри та ціни:"))
            for line in size_lines:
                rows.append((f"• {line}", f"• {esc(line)}"))
            if hidden:
                more = f"• …і ще {hidden} розмір(и) на сайті"
                rows.append((more, esc(more)))
        if content.custom_size_line:
            line = f"📏 {content.custom_size_line}"
            rows.append((line, f"📏 {esc(content.custom_size_line)}"))
        if content.price_line and not size_lines:
            line = f"🏷 Ціна: {content.price_line}"
            rows.append((line, f"🏷 Ціна: {esc(content.price_line)}"))

    spec_lines = content.spec_lines
    if specs_limit is not None:
        spec_lines = spec_lines[:specs_limit]
    if spec_lines:
        rows.append(("", ""))
        rows.append(("🧵 Характеристики:", "🧵 Характеристики:"))
        for line in spec_lines:
            rows.append((f"• {line}", f"• {esc(line)}"))

    # AR-тизер — маркетинговий бонус, трімається разом з friendly-блоком
    if include_ar and friendly and content.ar_available:
        rows.append(("", ""))
        rows.append((AR_TEASER, AR_TEASER))

    if with_url and content.url:
        rows.append(("", ""))
        rows.append(
            (
                f"👉 {CTA_TEXT}:\n{content.url}",
                f'👉 <a href="{esc(content.url)}">{CTA_TEXT}</a>',
            )
        )

    # `friendly` is the trim stage; allow_friendly_outro lets a caller keep the
    # AR teaser while supplying its own closing line (TikTok has one already).
    if friendly and allow_friendly_outro:
        rows.append(("", ""))
        rows.append((FRIENDLY_OUTRO, FRIENDLY_OUTRO))

    return rows


def render_plain(
    content: ProductPostContent,
    *,
    max_len: int,
    with_url: bool = True,
    include_ar: bool = True,
    allow_friendly_outro: bool = True,
) -> str:
    for specs_limit, sizes_limit, friendly in _TRIM_STAGES:
        rows = _rows(
            content,
            specs_limit=specs_limit,
            sizes_limit=sizes_limit,
            friendly=friendly,
            with_url=with_url,
            include_ar=include_ar,
            allow_friendly_outro=allow_friendly_outro,
        )
        text = "\n".join(plain for plain, _ in rows)
        if len(text) <= max_len:
            return text
    return text[:max_len]


def render_telegram_html(content: ProductPostContent, *, max_len: int = 1024) -> str:
    """TG рахує ліміт по видимому тексту, не по HTML-тегах —
    міряємо plain-версією, повертаємо HTML."""
    for specs_limit, sizes_limit, friendly in _TRIM_STAGES:
        rows = _rows(
            content,
            specs_limit=specs_limit,
            sizes_limit=sizes_limit,
            friendly=friendly,
            with_url=True,
        )
        visible = "\n".join(plain for plain, _ in rows)
        if len(visible) <= max_len:
            return "\n".join(html for _, html in rows)
    # останній stage і так мінімальний — віддаємо як є
    return "\n".join(html for _, html in rows)
