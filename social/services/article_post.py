"""Spec → scheduled carousel post announcing a blog article.

A spec is plain JSON, written by a person or an agent::

    {
      "hook": "Килим у дитячу: 4 речі, які варто знати",
      "tips": [{"title": "...", "text": "..."}, ...],      # 2-4 recommended
      "caption_ig": "... {link} ...",
      "caption_fb": "... {link} ...",
      "products": ["slug-1", "slug-2"]                      # optional
    }

``{link}`` is replaced per network with the article URL carrying that
network's UTM. Instagram does not make links in captions clickable, so its
caption always ends with a pointer to the profile link.

``schedule_article_post`` is idempotent on (article, scheduled_at): running
it again updates that post and re-renders its slides instead of creating a
second one. It uses the live models, so a data migration calling it must run
after the social/blog schema migrations it depends on.
"""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

KYIV = ZoneInfo("Europe/Kyiv")
IG_PROFILE_LINE = "Повна стаття за посиланням у профілі"
LINK_PLACEHOLDER = "{link}"

#: A post in one of these states has (or is) gone out: re-running a spec
#: must not touch it.
LOCKED_STATUSES = ("queued", "publishing", "published", "partial")


class SpecError(ValueError):
    pass


def parse_at(value) -> datetime:
    """'2026-12-01 18:00' (Kyiv) or a datetime (naive = Kyiv) → aware datetime."""
    if isinstance(value, datetime):
        moment = value
    else:
        text = str(value or "").strip().replace("T", " ")
        moment = None
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
            try:
                moment = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        if moment is None:
            raise SpecError(f"Не розумію дату «{value}». Формат: 2026-12-01 18:00 (Київ)")
    if timezone.is_naive(moment):
        moment = moment.replace(tzinfo=KYIV)
    return moment.replace(second=0, microsecond=0)


def normalize_spec(spec: dict) -> dict:
    if not isinstance(spec, dict):
        raise SpecError("spec має бути об'єктом JSON")
    tips = []
    for raw in spec.get("tips") or []:
        if not isinstance(raw, dict):
            raise SpecError("кожна порада: {\"title\": ..., \"text\": ...}")
        title = str(raw.get("title") or "").strip()
        text = str(raw.get("text") or "").strip()
        if title or text:
            tips.append({"title": title, "text": text})
    if len(tips) > 4:
        raise SpecError(f"порад {len(tips)}, максимум 4 (карусель має бути короткою)")
    products = [str(s).strip().lower() for s in (spec.get("products") or []) if str(s).strip()]
    return {
        "hook": str(spec.get("hook") or "").strip(),
        "tips": tips,
        "caption_ig": str(spec.get("caption_ig") or "").strip(),
        "caption_fb": str(spec.get("caption_fb") or "").strip(),
        "products": products[:3],
    }


def render_caption(template: str, link: str, *, platform: str) -> str:
    text = (template or "").strip()
    if LINK_PLACEHOLDER in text:
        text = text.replace(LINK_PLACEHOLDER, link)
    elif platform == "facebook" and link not in text:
        text = f"{text}\n\n{link}".strip()
    if platform == "instagram" and IG_PROFILE_LINE.lower() not in text.lower():
        text = f"{text}\n\n{IG_PROFILE_LINE}".strip()
    return text


def render_spec_slides(article, spec: dict):
    from blog.services.social_cards import CardSpec, render_article_slides

    return render_article_slides(
        article,
        CardSpec(hook=spec["hook"], tips=spec["tips"], products=spec["products"]),
    )


def schedule_article_post(article_slug: str, spec_dict: dict, at_datetime):
    """Render slides and create (or update) the scheduled SocialPost. Returns it."""
    from blog.models import Article
    from blog.services.social_cards import save_slides_to_storage, storage_dir
    from social.models import SocialPost, SocialPostImage
    from social.services.media_urls import article_campaign, article_share_url

    article = Article.objects.filter(slug=article_slug).first()
    if article is None:
        raise SpecError(f"Статті зі slug «{article_slug}» немає")
    spec = normalize_spec(spec_dict)
    at = parse_at(at_datetime)

    existing = SocialPost.objects.filter(article=article, scheduled_at=at).order_by("pk").first()
    if existing is not None and existing.status in LOCKED_STATUSES:
        logger.info("article post #%s already %s, left as is", existing.pk, existing.status)
        return existing

    campaign = article_campaign(article)[:64]
    caption_ig = render_caption(
        spec["caption_ig"], article_share_url(article, "instagram", campaign), platform="instagram"
    )
    caption_fb = render_caption(
        spec["caption_fb"] or spec["caption_ig"],
        article_share_url(article, "facebook", campaign),
        platform="facebook",
    )

    slides = render_spec_slides(article, spec)
    folder = storage_dir(article, at.astimezone(KYIV).strftime("%Y%m%d-%H%M"))
    names = save_slides_to_storage(slides, folder)

    with transaction.atomic():
        post = existing or SocialPost(article=article, scheduled_at=at)
        post.media_kind = SocialPost.MediaKind.PHOTOS
        post.product = None
        post.caption = caption_fb
        post.caption_ig = caption_ig
        post.caption_fb = caption_fb
        post.caption_tt = ""
        post.utm_campaign = campaign
        post.target_instagram = True
        post.target_facebook = True
        post.target_tiktok = False
        post.status = SocialPost.Status.SCHEDULED
        post.last_error = ""
        post.save()
        post.images.all().delete()
        for order, name in enumerate(names):
            img = SocialPostImage(post=post, sort_order=order)
            img.image.name = name
            img.save()
    return post
