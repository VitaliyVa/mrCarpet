"""Бейдж «Новинка» — прапорець is_new + вікно днів від created."""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone


def get_novelty_days() -> int:
    try:
        from .models import ShopSettings

        return int(ShopSettings.load().novelty_days or 0)
    except Exception:
        return 90


def product_is_novelty(product) -> bool:
    """
    True якщо товар позначений як новинка і ще в межах novelty_days від created.
    is_new=False — ручне вимкнення раніше строку.
    """
    if not getattr(product, "is_new", False):
        return False

    days = get_novelty_days()
    if days <= 0:
        return True

    created = getattr(product, "created", None)
    if not created:
        return True

    return timezone.now() <= created + timedelta(days=days)
