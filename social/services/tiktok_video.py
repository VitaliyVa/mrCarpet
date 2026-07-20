"""
Video generation for the TikTok auto-poster.

Two stages, because p-video derives its output aspect ratio from the input
image and ignores the aspect_ratio argument:

    4:3 interior photo -> gpt-image-2 -> 9:16 photo -> p-video -> 9:16 video

The 9:16 photo is generated once per product and reused for every later cycle,
so the recurring cost is the video alone. Draft mode is 4x cheaper but lets the
rug pattern drift between frames, which is unusable for a product ad — it stays
off outside tests.
"""

from __future__ import annotations

import io
import logging
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.core.files.base import ContentFile

from social.models import (
    SocialSettings,
    TikTokGenerationSpend,
    TikTokVerticalImage,
)
from social.services import tiktok_budget

logger = logging.getLogger(__name__)

PREDICTION_TIMEOUT_SEC = 600
POLL_INTERVAL_SEC = 3

VERTICAL_SIZE = "1152x2048"  # 9:16, the largest gpt-image-2 offers below 4K

# Strictly an extension, never a recomposition. The source scenes are already
# generated at the product's real physical scale, so moving, rescaling or
# re-framing the rug would misrepresent its size — a small mat must keep looking
# like a small mat.
REFRAME_PROMPT = (
    "Extend this interior photo vertically to a 9:16 composition. "
    "PRESERVE THE ORIGINAL IMAGE EXACTLY: keep every existing object — the rug, "
    "furniture, walls, floor — with identical pattern, colours, size, position, "
    "scale and perspective. Do not zoom, crop, re-centre, enlarge or emphasise "
    "anything. The original content must stay untouched in the middle of the frame. "
    "Only generate the missing area above and below it, continuing the same room, "
    "the same flooring, the same wall surfaces and the same lighting. "
    "Photorealistic interior photography, sharp and clean. "
    "No people, no text, no logos, no watermark, no new furniture."
)

# Barely-there motion: enough to feel alive, little enough that the woven
# pattern does not morph between the first and last frame.
VIDEO_PROMPT = (
    "Very slow, subtle camera push-in in a cozy sunlit living room. "
    "The rug stays still and sharp, its woven pattern unchanged throughout. "
    "Soft daylight shifts gently. Calm ambient background music. "
    "No people, no text, no logos, no watermark, no fast movement."
)


class TikTokVideoConfigError(RuntimeError):
    pass


class TikTokVideoError(RuntimeError):
    pass


def _client():
    token = (getattr(settings, "REPLICATE_API_TOKEN", "") or "").strip()
    if not token:
        raise TikTokVideoConfigError("REPLICATE_API_TOKEN empty")
    try:
        import replicate
    except ImportError as exc:  # pragma: no cover - packaging issue
        raise TikTokVideoConfigError("replicate package not installed") from exc
    return replicate.Client(api_token=token)


def _await_prediction(prediction, label: str):
    deadline = time.monotonic() + PREDICTION_TIMEOUT_SEC
    while prediction.status not in ("succeeded", "failed", "canceled"):
        if time.monotonic() > deadline:
            raise TikTokVideoError(f"{label}: timed out after {PREDICTION_TIMEOUT_SEC}s")
        time.sleep(POLL_INTERVAL_SEC)
        prediction.reload()
    if prediction.status != "succeeded":
        raise TikTokVideoError(f"{label}: {prediction.error or prediction.status}")
    return prediction


def _first_url(output) -> str:
    if isinstance(output, list):
        output = output[0] if output else None
    if output is None:
        return ""
    url = getattr(output, "url", None)
    if isinstance(url, str) and url.startswith("http"):
        return url
    text = str(output)
    return text if text.startswith("http") else ""


def _source_image(product):
    """The AI interior photo the vertical frame is built from."""
    return product.images.filter(is_ai=True).order_by("sort_order", "id").first()


def ensure_vertical_image(product, *, force: bool = False) -> TikTokVerticalImage:
    """
    Return the cached 9:16 frame for a product, generating it when missing.

    Charged once per product; later cycles reuse the stored file.
    """
    existing = TikTokVerticalImage.objects.filter(product=product).first()
    if existing and existing.image and not force:
        return existing

    source = _source_image(product)
    if source is None:
        raise TikTokVideoError(f"Product #{product.pk} has no is_ai photo")

    social = SocialSettings.load()
    model = (social.tiktok_vertical_image_model or "openai/gpt-image-2").strip()
    cost = tiktok_budget.image_cost()
    tiktok_budget.check_affordable(cost)

    source.image.open("rb")
    try:
        payload = source.image.read()
    finally:
        source.image.close()
    buf = io.BytesIO(payload)
    buf.name = Path(source.image.name).name or "source.png"

    client = _client()
    logger.info("TikTok 9:16 reframe start product=%s model=%s", product.pk, model)
    try:
        prediction = client.predictions.create(
            model=model,
            input={
                "prompt": REFRAME_PROMPT,
                "input_images": [buf],
                "aspect_ratio": VERTICAL_SIZE,
                "quality": "low",
                "output_format": "webp",
                "output_compression": 90,
                "background": "opaque",
                "number_of_images": 1,
            },
        )
        prediction = _await_prediction(prediction, "9:16 reframe")
        url = _first_url(prediction.output)
        if not url:
            raise TikTokVideoError(f"reframe returned no image: {prediction.output!r}")
        blob = requests.get(url, timeout=120)
        blob.raise_for_status()
    except Exception as exc:
        tiktok_budget.record(
            TikTokGenerationSpend.Kind.IMAGE,
            cost=cost,
            model_name=model,
            succeeded=False,
            note=str(exc)[:255],
        )
        raise

    tiktok_budget.record(
        TikTokGenerationSpend.Kind.IMAGE,
        cost=cost,
        model_name=model,
        succeeded=True,
        note=f"product={product.pk}",
    )

    record = existing or TikTokVerticalImage(product=product)
    record.source_image = source
    record.model_name = model
    record.image.save(f"tiktok-9x16-{product.pk}.webp", ContentFile(blob.content), save=False)
    record.save()
    logger.info("TikTok 9:16 reframe done product=%s", product.pk)
    return record


def generate_video_for_pick(pick, *, prompt: str = "", force: bool = False) -> str:
    """
    Generate the vertical video for a rotation pick and store it on the pick.

    Returns the saved media path. The MP4 is deleted only after TikTok reports
    PUBLISH_COMPLETE — pulling by URL is asynchronous on TikTok's side.
    """
    social = SocialSettings.load()
    if not social.tiktok_auto_enabled and not force:
        raise TikTokVideoConfigError("TikTok auto generation disabled in Social settings")
    if pick.product_id is None:
        raise TikTokVideoError("Pick has no product")

    vertical = ensure_vertical_image(pick.product)

    seconds = int(social.tiktok_video_seconds or 6)
    resolution = (social.tiktok_video_resolution or "720p").strip()
    draft = bool(social.tiktok_video_draft)
    model = (social.tiktok_video_model or "prunaai/p-video").strip()

    cost = tiktok_budget.video_cost(seconds, resolution, draft)
    tiktok_budget.check_affordable(cost)

    # Upload the frame rather than pointing at its public URL: in development
    # the media file is not reachable from the internet, and in production it
    # removes a dependency on the file being served at that exact moment.
    vertical.image.open("rb")
    try:
        frame = io.BytesIO(vertical.image.read())
    finally:
        vertical.image.close()
    frame.name = Path(vertical.image.name).name or "frame.webp"

    client = _client()
    logger.info(
        "TikTok video start pick=%s model=%s %ss %s draft=%s",
        pick.pk, model, seconds, resolution, draft,
    )
    try:
        output = client.run(
            model,
            input={
                "image": frame,
                "prompt": (prompt or VIDEO_PROMPT).strip(),
                "duration": seconds,
                "resolution": resolution,
                "fps": 24,
                "draft": draft,
                "save_audio": True,
                "prompt_upsampling": False,
            },
        )
        url = _first_url(output)
        if not url:
            raise TikTokVideoError(f"video model returned no URL: {output!r}")
        blob = requests.get(url, timeout=240)
        blob.raise_for_status()
    except Exception as exc:
        tiktok_budget.record(
            TikTokGenerationSpend.Kind.VIDEO,
            cost=cost,
            model_name=model,
            succeeded=False,
            pick=pick,
            note=str(exc)[:255],
        )
        raise

    tiktok_budget.record(
        TikTokGenerationSpend.Kind.VIDEO,
        cost=cost,
        model_name=model,
        succeeded=True,
        pick=pick,
        note=f"product={pick.product_id}",
    )

    name = Path(urlparse(url).path).name or "tiktok.mp4"
    if not name.lower().endswith(".mp4"):
        name = f"{name}.mp4"

    from django.core.files.storage import default_storage

    path = default_storage.save(
        f"social/tiktok/video/pick-{pick.pk}-{name}", ContentFile(blob.content)
    )
    pick.video_path = path
    pick.save(update_fields=["video_path", "updated"])
    logger.info("TikTok video done pick=%s path=%s", pick.pk, path)
    return path
