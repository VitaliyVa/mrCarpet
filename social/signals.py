"""Product → TG channel auto-post."""

from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender="catalog.Product")
def maybe_post_new_product_to_tg(sender, instance, created, **kwargs):
    if not created:
        return
    try:
        from social.models import SocialSettings
        from social.services.telegram_products import enqueue_product_channel_post

        social = SocialSettings.load()
        if not social.auto_post_new_products_tg:
            return
        if not (social.products_channel_id or "").strip():
            return
        enqueue_product_channel_post(instance.pk)
    except Exception:
        # Never break product save
        import logging

        logging.getLogger(__name__).exception("social product signal failed")
