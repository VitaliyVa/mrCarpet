"""Product → SocialPost (IG/FB photos) builder + auto-post.

Дзеркало telegram_products для Meta: з товару збирається photos-пост
(головне фото + галерея), caption = назва + розміри/ціни. Файли не
копіюються — SocialPostImage.image.name вказує на існуючі файли в media,
absolute_media_url віддасть їх Meta-краулеру як публічні HTTPS URL.
"""

from __future__ import annotations

import logging
import threading

from django.db import close_old_connections, transaction

from social.models import SocialPost, SocialPostImage

logger = logging.getLogger(__name__)

MAX_IMAGES = 10  # ліміт IG carousel

# utm-мітка авто-постів; також ключ ідемпотентності (не постити товар двічі)
AUTO_CAMPAIGN = "new-product"

# default-заглушка Product.image — не контент для соцмереж
PLACEHOLDER_IMAGE = "products/default.png"


def product_caption_text(product) -> str:
    """Plain-caption для IG/FB (SocialPost.caption): повний контент
    без лінка — його додає build_caption при publish (utm-версію).
    """
    from social.services.post_content import build_product_content, render_plain

    return render_plain(
        build_product_content(product), max_len=2000, with_url=False
    )


def _product_image_names(product) -> list[str]:
    """Storage-імена (media-відносні) головного фото + галереї, dedup, max 10."""
    names: list[str] = []
    seen: set[str] = set()

    def _add(field) -> None:
        if not field:
            return
        name = getattr(field, "name", "") or ""
        if not name or name == PLACEHOLDER_IMAGE or name in seen:
            return
        seen.add(name)
        names.append(name)

    _add(getattr(product, "image", None))
    try:
        extras = product.images.order_by("sort_order", "id")
    except Exception:
        extras = []
    for img in extras:
        _add(getattr(img, "image", None))
        if len(names) >= MAX_IMAGES:
            break
    return names[:MAX_IMAGES]


def build_product_social_post(
    product,
    *,
    target_instagram: bool = True,
    target_facebook: bool = True,
) -> SocialPost:
    """Створює draft SocialPost (photos) з фото товару. Публікація окремо."""
    names = _product_image_names(product)
    if not names:
        raise ValueError(f"«{product}»: у товару немає фото — нема що постити")
    post = SocialPost.objects.create(
        product=product,
        media_kind=SocialPost.MediaKind.PHOTOS,
        caption=product_caption_text(product),
        utm_campaign=AUTO_CAMPAIGN,
        target_instagram=target_instagram,
        target_facebook=target_facebook,
        target_tiktok=False,
    )
    for i, name in enumerate(names):
        img = SocialPostImage(post=post, sort_order=i)
        img.image.name = name
        img.save()
    return post


def has_auto_post(product_id: int) -> bool:
    """Чи вже є (не-failed) авто-пост для товару — захист від дублю сигналу."""
    return (
        SocialPost.objects.filter(
            product_id=product_id, utm_campaign=AUTO_CAMPAIGN
        )
        .exclude(status=SocialPost.Status.FAILED)
        .exists()
    )


def enqueue_product_meta_post(product_id: int) -> None:
    """Авто-режим: після коміту створити пост і одразу опублікувати.

    on_commit — щоб worker-тред бачив і товар, і inline-галерею
    (адмінка комітить їх однією транзакцією), як у TG-автопості.
    """

    def _run():
        close_old_connections()
        try:
            from catalog.models import Product
            from social.services.publish import (
                publish_post,
                validate_post_for_publish,
            )

            product = Product.objects.filter(pk=product_id).first()
            if not product:
                logger.warning(
                    "Meta product post skipped: Product pk=%s not found",
                    product_id,
                )
                return
            if has_auto_post(product_id):
                logger.info(
                    "Meta product post skipped: already exists pk=%s",
                    product_id,
                )
                return
            post = build_product_social_post(product)
            err = validate_post_for_publish(post)
            if err:
                post.status = SocialPost.Status.FAILED
                post.last_error = err
                post.save(update_fields=["status", "last_error", "updated"])
                logger.error(
                    "Meta product post invalid pk=%s: %s", product_id, err
                )
                return
            post.status = SocialPost.Status.QUEUED
            post.save(update_fields=["status", "updated"])
            publish_post(post.pk)
        except Exception:
            logger.exception("Meta product auto-post failed pk=%s", product_id)
        finally:
            close_old_connections()

    def _schedule():
        threading.Thread(target=_run, daemon=True).start()

    transaction.on_commit(_schedule)
