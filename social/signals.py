"""Product → TG channel + Meta (IG/FB) + Viber auto-post."""

from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver


def _autopost_wanted(instance, settings_flag: bool) -> bool:
    """Чи постити цей товар.

    `_social_autopost_choice` виставляє адмінка (галочка «Опублікувати в
    соцмережах» на формі створення) — явний вибір людини має пріоритет над
    глобальним авто-toggle. Якщо атрибута немає (товар створений скриптом,
    імпортом чи API), працює глобальна налаштування як раніше.
    """
    choice = getattr(instance, "_social_autopost_choice", None)
    if choice is None:
        return bool(settings_flag)
    return bool(choice)


@receiver(post_save, sender="catalog.Product")
def maybe_post_new_product_to_socials(sender, instance, created, **kwargs):
    # Тільки створення. Редагування наявного товару НІКОЛИ не постить повторно.
    if not created:
        return
    try:
        from social.models import SocialSettings

        social = SocialSettings.load()
    except Exception:
        import logging

        logging.getLogger(__name__).exception("social settings load failed")
        return

    # Telegram products channel
    try:
        if (
            _autopost_wanted(instance, social.auto_post_new_products_tg)
            and (social.products_channel_id or "").strip()
        ):
            from social.services.telegram_products import (
                enqueue_product_channel_post,
            )

            enqueue_product_channel_post(instance.pk)
    except Exception:
        # Never break product save
        import logging

        logging.getLogger(__name__).exception("TG product signal failed")

    # Meta: Instagram / Facebook
    try:
        if _autopost_wanted(instance, social.auto_post_new_products_meta):
            from social.services import meta
            from social.services.product_post import enqueue_product_meta_post

            if meta.meta_configured(need_ig=True) or meta.meta_configured(
                need_fb=True
            ):
                enqueue_product_meta_post(instance.pk)
    except Exception:
        import logging

        logging.getLogger(__name__).exception("Meta product signal failed")

    # Viber channel — майстер-рубильник поважаємо завжди, галочка його не обходить
    try:
        if social.viber_posting_enabled and _autopost_wanted(
            instance, social.auto_post_new_products_viber
        ):
            from social.services.viber_products import (
                enqueue_product_viber_post,
                viber_configured,
            )

            if viber_configured():
                enqueue_product_viber_post(instance.pk)
    except Exception:
        import logging

        logging.getLogger(__name__).exception("Viber product signal failed")
