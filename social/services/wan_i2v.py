"""Replicate Wan image-to-video drafts for product ads."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.core.files.base import ContentFile

from social.models import SocialAiGenerationLog, SocialPost, SocialSettings
from social.services.media_urls import absolute_media_url

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "wan-video/wan-2.2-i2v-fast"
DEFAULT_PROMPT = (
    "Photorealistic product video of a soft area rug on a wooden floor, "
    "slow gentle camera push-in, soft natural daylight, cozy living room, "
    "no text, no logos, no watermark, high detail fabric texture"
)


class WanConfigError(RuntimeError):
    pass


class WanBudgetError(RuntimeError):
    pass


class WanGenerateError(RuntimeError):
    pass


def _token() -> str:
    return (getattr(settings, "REPLICATE_API_TOKEN", None) or "").strip()


def _model_name(social: SocialSettings | None = None) -> str:
    social = social or SocialSettings.load()
    return (
        (social.ai_i2v_model or "").strip()
        or (getattr(settings, "SOCIAL_AI_I2V_MODEL", "") or "").strip()
        or DEFAULT_MODEL
    )


def generate_draft_from_product(
    post: SocialPost,
    *,
    prompt: str = "",
    force: bool = False,
) -> SocialPost:
    """
    Generate MP4 from product.image via Wan I2V, attach to post, mark ai_generated.
    Does NOT auto-publish — admin must review and click Publish.
    """
    social = SocialSettings.load()
    if not social.ai_i2v_enabled and not force:
        raise WanConfigError("AI I2V disabled in Social settings")
    if not _token():
        raise WanConfigError("REPLICATE_API_TOKEN empty")
    if not post.product_id or not post.product.image:
        raise WanGenerateError("Post needs product with image")

    used = SocialAiGenerationLog.today_count()
    limit = int(social.ai_i2v_daily_limit or 10)
    if used >= limit and not force:
        raise WanBudgetError(f"Daily AI I2V limit reached ({limit})")

    image_url = absolute_media_url(post.product.image)
    if not image_url.startswith("https://") and not image_url.startswith("http://"):
        raise WanGenerateError(f"Invalid product image URL: {image_url}")

    # Local/dev http may fail Replicate fetch — still try; prod is HTTPS.
    final_prompt = (prompt or post.ai_prompt or DEFAULT_PROMPT).strip()
    model = _model_name(social)

    try:
        import replicate
    except ImportError as exc:
        raise WanConfigError("replicate package not installed") from exc

    client = replicate.Client(api_token=_token())
    logger.info("Wan I2V start model=%s post=%s", model, post.pk)
    try:
        output = client.run(
            model,
            input={
                "image": image_url,
                "prompt": final_prompt,
                # Common Wan I2V knobs — ignored if model schema differs
                "num_frames": 81,
                "fps": 16,
            },
        )
    except Exception as exc:
        raise WanGenerateError(f"Replicate run failed: {exc}") from exc

    video_url = _extract_url(output)
    if not video_url:
        raise WanGenerateError(f"No video URL in output: {output!r}")

    blob = requests.get(video_url, timeout=120)
    blob.raise_for_status()
    name = Path(urlparse(video_url).path).name or "wan-draft.mp4"
    if not name.lower().endswith(".mp4"):
        name = f"{name}.mp4"

    post.video.save(name, ContentFile(blob.content), save=False)
    post.ai_generated = True
    post.ai_prompt = final_prompt
    if not post.caption and post.product_id:
        post.caption = _default_caption(post)
    post.save()
    SocialAiGenerationLog.increment_today()
    return post


def _default_caption(post: SocialPost) -> str:
    title = post.product.title if post.product_id else "Килим"
    promo = (post.promo_code or "").strip()
    line = f"{title} — mr.Carpet"
    if promo:
        line += f"\nПромокод {promo}"
    return line


def _extract_url(output: Any) -> str:
    if output is None:
        return ""
    if isinstance(output, str) and output.startswith("http"):
        return output
    if isinstance(output, list) and output:
        return _extract_url(output[0])
    # FileOutput-like
    url = getattr(output, "url", None)
    if isinstance(url, str) and url.startswith("http"):
        return url
    return str(output) if str(output).startswith("http") else ""
