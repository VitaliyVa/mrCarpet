"""Product → TG channel + Meta (IG/FB) auto-post."""

from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender="catalog.Product")
def maybe_post_new_product_to_socials(sender, instance, created, **kwargs):
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
            social.auto_post_new_products_tg
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
        if social.auto_post_new_products_meta:
            from social.services import meta
            from social.services.product_post import enqueue_product_meta_post

            if meta.meta_configured(need_ig=True) or meta.meta_configured(
                need_fb=True
            ):
                enqueue_product_meta_post(instance.pk)
    except Exception:
        import logging

        logging.getLogger(__name__).exception("Meta product signal failed")
