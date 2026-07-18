"""Підписка / відписка на розсилку (Subscription)."""

from __future__ import annotations

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from project.email_branding import site_url
from project.models import Subscription


def unsubscribe_absolute_url(subscription: Subscription) -> str:
    path = reverse(
        "newsletter_unsubscribe",
        kwargs={"token": subscription.unsubscribe_token},
    )
    return f"{site_url()}{path}"


def get_or_link_subscription_for_user(user) -> Subscription | None:
    """Знайти підписку за email юзера і прив’язати user FK."""
    email = (getattr(user, "email", None) or "").strip().lower()
    if not email:
        return None
    sub = Subscription.objects.filter(email__iexact=email).first()
    if not sub:
        return None
    if sub.user_id != user.pk:
        sub.user = user
        sub.save(update_fields=["user"])
    return sub


@transaction.atomic
def subscribe_email(
    email: str,
    *,
    source: str = Subscription.SOURCE_FOOTER,
    user=None,
) -> tuple[Subscription, str]:
    """
    Підписати / реактивувати.
    Returns: (subscription, status) where status is 'created' | 'reactivated' | 'already_active'.
    """
    email = (email or "").strip().lower()
    if not email:
        raise ValueError("Email обовʼязковий")

    sub = Subscription.objects.filter(email__iexact=email).first()
    if sub is None:
        sub = Subscription.objects.create(
            email=email,
            user=user,
            is_active=True,
            source=source,
            unsubscribed_at=None,
        )
        return sub, "created"

    updates = []
    if user and sub.user_id != getattr(user, "pk", None):
        sub.user = user
        updates.append("user")

    if sub.is_active:
        if updates:
            sub.save(update_fields=updates)
        return sub, "already_active"

    sub.is_active = True
    sub.unsubscribed_at = None
    sub.subscribed_at = timezone.now()
    sub.source = source
    updates.extend(["is_active", "unsubscribed_at", "subscribed_at", "source"])
    sub.save(update_fields=list(dict.fromkeys(updates)))
    return sub, "reactivated"


@transaction.atomic
def unsubscribe_subscription(subscription: Subscription) -> Subscription:
    if not subscription.is_active:
        return subscription
    subscription.is_active = False
    subscription.unsubscribed_at = timezone.now()
    subscription.save(update_fields=["is_active", "unsubscribed_at"])
    return subscription


def set_newsletter_enabled(user, enabled: bool) -> Subscription:
    """Toggle з кабінету: create/reactivate або unsubscribe."""
    email = (user.email or "").strip().lower()
    if not email:
        raise ValueError("У профілі немає email")

    if enabled:
        sub, _ = subscribe_email(
            email, source=Subscription.SOURCE_PROFILE, user=user
        )
        return sub

    sub = Subscription.objects.filter(email__iexact=email).first()
    if sub is None:
        # Немає запису — вважаємо вже «вимкнено»; створюємо inactive для консистентності
        sub = Subscription.objects.create(
            email=email,
            user=user,
            is_active=False,
            source=Subscription.SOURCE_PROFILE,
            unsubscribed_at=timezone.now(),
        )
        return sub
    if sub.user_id != user.pk:
        sub.user = user
        sub.save(update_fields=["user"])
    return unsubscribe_subscription(sub)
