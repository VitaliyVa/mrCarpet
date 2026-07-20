"""
On-screen copy for the TikTok guess-the-price format.

The format asks the viewer to value the rug, counts down, then reveals the
price. It earns comments — the signal TikTok weighs most — and gives the six
second clip a job to do beyond looking pretty.

Phrasings rotate: running the same sentence for fifty days straight is what
makes an account read as a bot. The variant is picked deterministically from
the pick id, so regenerating a video reproduces the same script.
"""

from __future__ import annotations

import random
import re
from decimal import Decimal

# The question names the exact size so the guess is anchored to the variant
# whose price is revealed; without it viewers price what they see in the room.
# It also names the currency — without it the guess is ambiguous.
HOOKS = (
    "Скільки гривень ви б дали за такий килим {size}?",
    "У скільки ₴ ви б оцінили цей килим {size}?",
    "Скільки гривень заплатили б за такий килим {size}?",
    "Як думаєте, скільки гривень коштує килим {size}?",
    "Скільки, по-вашому, коштує цей килим {size} у гривнях?",
)

CTAS = (
    "Пишіть свої здогадки в коментарях 👇",
    "Хто вгадав — пишіть у коментарях 👇",
    "Ваші варіанти пишіть у коментарях 👇",
    "Напишіть у коментарях, чи вгадали 👇",
    "Хто назвав більше — пишіть у коментарях 👇",
)

COUNTDOWN = ("3", "2", "1")


def normalise_size(label: str) -> str:
    """
    '0.8х1.5' / '0.5x0.8' -> '0.8 × 1.5 м'.

    The catalogue mixes the Cyrillic 'х' and the Latin 'x' as the separator,
    so both are accepted and rendered with a proper multiplication sign.
    """
    text = (label or "").strip()
    if not text:
        return ""
    parts = re.split(r"[xхX×]", text)
    parts = [p.strip().replace(",", ".") for p in parts if p.strip()]
    if len(parts) != 2:
        return text
    return f"{parts[0]} × {parts[1]} м"


def format_price(value) -> str:
    """
    475 -> '475 ₴', 2300 -> '2 300 ₴'.

    A plain space, not U+2009: the montage draws this through ffmpeg and not
    every font carries a thin-space glyph.
    """
    if value is None:
        return ""
    amount = int(Decimal(str(value)))
    return f"{amount:,}".replace(",", " ") + " ₴"


def first_priced_attribute(product):
    """
    The variant whose price the video reveals.

    Meta.ordering puts the smallest width first, and 40 of the 50 eligible
    products have exactly one size, so this is normally the only choice.
    """
    for attr in product.product_attr.filter(custom_attribute=False):
        if attr.price:
            return attr
    return None


def build_script(pick) -> dict:
    """
    Return the on-screen copy for a rotation pick.

    Raises ValueError when the product has no priced size — the guess-the-price
    format cannot run without an answer to reveal.
    """
    product = pick.product
    if product is None:
        raise ValueError("Pick has no product")

    attr = first_priced_attribute(product)
    if attr is None:
        raise ValueError(f"Product #{product.pk} has no priced size")

    size = normalise_size(attr.size.title if attr.size else "")
    if not size:
        raise ValueError(f"Product #{product.pk} first size has no label")

    rng = random.Random(pick.pk or 0)
    return {
        "hook": rng.choice(HOOKS).format(size=size),
        "countdown": COUNTDOWN,
        "price": format_price(attr.price),
        "cta": rng.choice(CTAS),
        "size": size,
        "price_value": int(attr.price),
    }
