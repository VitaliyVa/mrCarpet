"""Промокоди: валідація терміну дії та лімітів використань."""

from __future__ import annotations

from django.db.models import Q
from django.utils import timezone

from catalog.models import PromoCode


class PromoCodeError(Exception):
    """Бізнес-помилка застосування промокоду (текст для клієнта)."""


def normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


def find_promocode(code: str, *, for_update: bool = False) -> PromoCode | None:
    qs = PromoCode.objects.all()
    if for_update:
        qs = qs.select_for_update()
    return qs.filter(code__iexact=(code or "").strip()).first()


def _identity_q(*, user=None, email: str | None = None) -> Q | None:
    email = normalize_email(email)
    q = Q()
    has = False
    if email:
        q |= Q(email__iexact=email)
        has = True
    if user is not None and getattr(user, "is_authenticated", False) and user.pk:
        q |= Q(user=user)
        user_email = normalize_email(getattr(user, "email", None))
        if user_email:
            q |= Q(email__iexact=user_email)
        has = True
    return q if has else None


def validate_promocode(
    promo: PromoCode,
    *,
    user=None,
    email: str | None = None,
    require_identity: bool = False,
    exclude_order_id: int | None = None,
) -> None:
    """
    Перевіряє термін дії + ліміти.
    require_identity=True — на оформленні замовлення (потрібен email/user для per-user).
    exclude_order_id — не рахувати поточне замовлення (пост-перевірка після insert).
    """
    if promo.end_time is not None and promo.end_time < timezone.now():
        raise PromoCodeError("Промокод не знайдено або термін дії закінчився")

    redemptions = promo.active_redemptions()
    if exclude_order_id is not None:
        redemptions = redemptions.exclude(order_id=exclude_order_id)

    if promo.max_uses_total is not None:
        if redemptions.count() >= promo.max_uses_total:
            raise PromoCodeError("Промокод вичерпано")

    if promo.max_uses_per_user is not None:
        identity = _identity_q(user=user, email=email)
        if identity is None:
            if require_identity:
                raise PromoCodeError(
                    "Вкажіть email, щоб застосувати цей промокод"
                )
        else:
            used = redemptions.filter(identity).count()
            if used >= promo.max_uses_per_user:
                raise PromoCodeError("Ви вже використали цей промокод")


def resolve_and_validate(
    code: str,
    *,
    user=None,
    email: str | None = None,
    require_identity: bool = False,
    for_update: bool = False,
) -> PromoCode:
    promo = find_promocode(code, for_update=for_update)
    if not promo:
        raise PromoCodeError("Промокод не знайдено або термін дії закінчився")
    validate_promocode(
        promo,
        user=user,
        email=email,
        require_identity=require_identity,
    )
    return promo


def _lock_promocode_row(promo: PromoCode) -> None:
    """
    select_for_update() на SQLite — no-op (Django 4.2 docs).
    UPDATE рядка форсує write-lock у транзакції і серіалізує конкурентні apply.
    """
    PromoCode.objects.filter(pk=promo.pk).update(updated=timezone.now())


def apply_promocode_to_order(
    order,
    code: str,
    *,
    user=None,
) -> PromoCode:
    """
    Валідує, пише FK + snapshot на order, створює redemption.
    Викликати всередині transaction.atomic().
    """
    from order.models import PromoCodeRedemption

    email = normalize_email(order.email)
    promo = find_promocode(code, for_update=True)
    if not promo:
        raise PromoCodeError("Промокод не знайдено або термін дії закінчився")

    _lock_promocode_row(promo)
    promo.refresh_from_db()

    validate_promocode(
        promo,
        user=user,
        email=email,
        require_identity=True,
    )

    order.promocode = promo
    order.promocode_code = promo.code
    order.promocode_discount = promo.discount

    PromoCodeRedemption.objects.create(
        promocode=promo,
        order=order,
        user=(
            user
            if user is not None and getattr(user, "is_authenticated", False)
            else None
        ),
        email=email,
    )

    # Повторна перевірка після insert (без поточного order) — ловить гонку на SQLite
    validate_promocode(
        promo,
        user=user,
        email=email,
        require_identity=True,
        exclude_order_id=order.pk,
    )
    return promo
