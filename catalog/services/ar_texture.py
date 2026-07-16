"""Generate AR texture from catalog Product.image via Bria product-cutout + Pillow crop."""

from __future__ import annotations

import io
import logging
import time
from pathlib import Path

import replicate
import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone
from PIL import Image

from catalog.services.make_glb import detect_image
from catalog.services.replicate_product_images import (
    ReplicateGenerationError,
    ReplicateJobLog,
)

logger = logging.getLogger("catalog.ar")

# bria/product-cutout — eCommerce cutout with soft (256-level) alpha
CUTOUT_MODEL = "bria/product-cutout"
CUTOUT_VERSION = "fa93ba905ce997429b6bbbdb7e63cc1e986c71bd1fabd3d8f4a8be9c7eeba2e1"
PREDICTION_TIMEOUT_SEC = 180
POLL_INTERVAL_SEC = 2
ALPHA_THRESHOLD = 16
MAX_TEXTURE_EDGE = 2048


def tight_crop_rgba(img: Image.Image, alpha_threshold: int = ALPHA_THRESHOLD) -> Image.Image:
    """Crop to non-transparent bbox. Keeps RGBA."""
    rgba = img.convert("RGBA")
    alpha = rgba.split()[-1]
    mask = alpha.point(lambda a: 255 if a >= alpha_threshold else 0)
    bbox = mask.getbbox()
    if not bbox:
        return rgba
    return rgba.crop(bbox)


def prepare_ar_texture_png(raw_bytes: bytes) -> bytes:
    """Ensure PNG RGBA, tight-cropped, optionally downscaled. Never flatten alpha."""
    img = Image.open(io.BytesIO(raw_bytes))
    cropped = tight_crop_rgba(img)

    w, h = cropped.size
    longest = max(w, h)
    if longest > MAX_TEXTURE_EDGE:
        scale = MAX_TEXTURE_EDGE / longest
        cropped = cropped.resize(
            (max(1, round(w * scale)), max(1, round(h * scale))),
            Image.Resampling.LANCZOS,
        )

    buf = io.BytesIO()
    cropped.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


class ArTextureService:
    """Remove background from catalog image and store as Product.ar_texture."""

    def __init__(self):
        token = settings.REPLICATE_API_TOKEN
        if not token:
            raise ReplicateGenerationError(
                "REPLICATE_API_TOKEN не налаштовано. Додайте токен у .env"
            )
        self.client = replicate.Client(api_token=token)
        self.job_log = ReplicateJobLog()

    def generate_for_product(self, product) -> dict:
        from catalog.models import Product

        if not product.image:
            raise ReplicateGenerationError("У товару немає каталожного зображення")

        product.ar_status = Product.AR_STATUS_PENDING
        product.ar_error = ""
        product.save(update_fields=["ar_status", "ar_error"])

        started = time.monotonic()
        try:
            with product.image.open("rb") as src:
                source_bytes = src.read()
            source_name = Path(product.image.name).name or "catalog.webp"

            self.job_log.info(f"AR: {CUTOUT_MODEL} — зняття фону…")
            cutout_bytes = self._run_cutout(source_bytes, source_name)

            self.job_log.info("AR: crop по alpha…")
            png_bytes = prepare_ar_texture_png(cutout_bytes)
            mime, has_alpha = detect_image(png_bytes)
            self.job_log.info(
                f"AR: текстура {len(png_bytes) // 1024} KB ({mime}, alpha={has_alpha})"
            )

            filename = f"ar-{product.pk}-{int(time.time())}.png"
            if product.ar_texture:
                product.ar_texture.delete(save=False)
            product.ar_texture.save(filename, ContentFile(png_bytes), save=False)
            product.ar_status = Product.AR_STATUS_READY
            product.ar_error = ""
            product.ar_updated_at = timezone.now()
            product.save(
                update_fields=[
                    "ar_texture",
                    "ar_status",
                    "ar_error",
                    "ar_updated_at",
                ]
            )

            from catalog.services.ar_glb_cache import clear_product_glb_cache, pregenerate_product_glbs

            clear_product_glb_cache(product.pk)
            glb_meta = pregenerate_product_glbs(product)

            duration = round(time.monotonic() - started, 1)
            self.job_log.ok(f"AR: готово за {duration} с")

            return {
                "success": True,
                "ar_status": product.ar_status,
                "ar_texture_url": product.ar_texture.url if product.ar_texture else None,
                "duration_sec": duration,
                "model": CUTOUT_MODEL,
                "glb": glb_meta,
                "logs": self.job_log.entries,
            }
        except Exception as exc:
            product.ar_status = Product.AR_STATUS_FAILED
            product.ar_error = str(exc)[:2000]
            product.ar_updated_at = timezone.now()
            product.save(update_fields=["ar_status", "ar_error", "ar_updated_at"])
            self.job_log.error(str(exc))
            raise

    def _run_cutout(self, source_bytes: bytes, source_name: str) -> bytes:
        file_obj = io.BytesIO(source_bytes)
        file_obj.name = source_name

        prediction = self.client.predictions.create(
            version=CUTOUT_VERSION,
            input={
                "image": file_obj,
                "preserve_alpha": True,
                "force_rmbg": True,
                "content_moderation": False,
            },
        )
        logger.info("AR cutout (%s): prediction id=%s", CUTOUT_MODEL, prediction.id)

        prediction = self._poll(prediction)

        if prediction.status != "succeeded":
            error = prediction.error or "Невідома помилка product-cutout"
            raise ReplicateGenerationError(error)

        output = prediction.output
        if not output:
            raise ReplicateGenerationError("product-cutout не повернув зображення")

        url = output[0] if isinstance(output, list) else output
        response = requests.get(url, timeout=120)
        response.raise_for_status()
        return response.content

    def _poll(self, prediction):
        deadline = time.monotonic() + PREDICTION_TIMEOUT_SEC
        last_status = None
        while prediction.status not in ("succeeded", "failed", "canceled"):
            if time.monotonic() > deadline:
                try:
                    prediction.cancel()
                except Exception as exc:
                    logger.error("Cancel cutout failed: %s", exc)
                raise ReplicateGenerationError(
                    f"Таймаут {CUTOUT_MODEL} ({PREDICTION_TIMEOUT_SEC} с). id={prediction.id}"
                )
            if prediction.status != last_status:
                last_status = prediction.status
                logger.info("AR cutout status=%s", prediction.status)
            time.sleep(POLL_INTERVAL_SEC)
            prediction.reload()
        return prediction


def mark_ar_ready_from_manual_upload(product) -> None:
    """After manual ar_texture upload in admin — mark ready and rebuild GLBs."""
    from catalog.models import Product
    from catalog.services.ar_glb_cache import clear_product_glb_cache, pregenerate_product_glbs

    if not product.ar_texture:
        product.ar_status = Product.AR_STATUS_NONE
        product.save(update_fields=["ar_status"])
        return

    product.ar_status = Product.AR_STATUS_READY
    product.ar_error = ""
    product.ar_updated_at = timezone.now()
    product.save(update_fields=["ar_status", "ar_error", "ar_updated_at"])
    clear_product_glb_cache(product.pk)
    pregenerate_product_glbs(product)
