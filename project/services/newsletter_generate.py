"""Generate email-safe inner HTML + optional hero image for NewsletterCampaign."""

from __future__ import annotations

import html as html_lib
import logging
import time
from dataclasses import dataclass
from typing import Any

import replicate
import requests
from django.conf import settings
from django.core.files.base import ContentFile

from catalog.image_optimize import optimize_product_image
from project.email_branding import site_url
from project.models import NewsletterCampaign
from project.replicate_utils import extract_json_object, poll_prediction
from project.services.newsletter_html_sanitize import sanitize_newsletter_html

logger = logging.getLogger(__name__)

TEXT_MODEL = "openai/gpt-4o-mini"
IMAGE_MODEL = "openai/gpt-image-2"
IMAGE_QUALITY = "low"
IMAGE_ASPECT = "16:9"
IMAGE_MAX_WIDTH = 960
IMAGE_WEBP_QUALITY = 90
PREDICTION_TIMEOUT_SEC = 120
IMAGE_TIMEOUT_SEC = 180
POLL_INTERVAL_SEC = 2
BRIEF_MIN_LEN = 10
BRIEF_MAX_LEN = 4000

SYSTEM_PROMPT = """Ти email-верстальник і копірайтер для українського магазину килимів mr.Carpet.

Завдання: з брифу менеджера зібрати INNER HTML тіла листа (не повний документ) + промпт для hero-фото.

Критичні правила (поштовики: Gmail, Outlook, Apple Mail):
1. ТІЛЬКИ table[role=presentation], tr, td, p, span, strong, em, b, i, a, br, img, ul/ol/li, div.
2. Без <!DOCTYPE>, <html>, <head>, <body>, <style>, script, iframe, flex, grid, position.
3. Усі стилі — INLINE (style="..."). Основний шрифт: Arial, Helvetica, sans-serif.
4. Кольори бренду:
   - текст #453f3a
   - акцент/CTA bgcolor #a46c46, текст на CTA #fffcf2
   - м’який акцент тексту #a46c46 або #8b5e3c
   - другорядний текст #6b635c
   - фон акцентного блоку #f3ebe3
5. Посилання абсолютні https://… CTA — table-кнопка (td bgcolor + <a>), не <button>.
6. НЕ вставляй <img> сам і НЕ додавай лінк відписки — їх додасть сервер.
7. Українською. Не вигадуй ціни/знижки/дати, яких немає в брифі.
8. Зовнішній header з логотипом НЕ роби — він уже в шаблоні сайту.

Структура й стиль (обов’язково «живий» лист, не сухий абзац):
- Привітання окремим рядком (більший кегль або accent color).
- 3–5 коротких абзаців / блоків (не один суцільний текст).
- Хоча б один акцент: span/strong з color:#a46c46 або bgcolor-блок #f3ebe3.
- Список переваг (ul/li) з 3–5 пунктів, якщо бриф це дозволяє.
- Чіткий CTA-кнопка з конкретною дією + URL з брифу (або https://mrcarpet24.com/catalog/).
- Фінальний м’який заклик (1 речення).
- Обсяг видимого тексту: орієнтир 450–900 символів (без тегів).

image_prompt:
- АНГЛІЙСЬКОЮ, 1–2 речення.
- Photorealistic interior / rug lifestyle, soft natural light.
- No logos, no watermarks, no readable text, no people faces if avoidable.

Відповідь СТРОГО одним JSON:
{"subject":"...","preheader":"...","image_prompt":"...","body_html":"<table role=\\"presentation\\"...>...</table>"}
"""


class NewsletterGenerationError(Exception):
    pass


@dataclass(frozen=True)
class NewsletterGenerationResult:
    campaign_id: int
    subject: str
    model: str
    duration_sec: float
    image_generated: bool = False


def _normalize_brief(brief: str) -> str:
    text = " ".join((brief or "").split()).strip()
    if len(text) < BRIEF_MIN_LEN:
        raise NewsletterGenerationError(
            f"Бриф занадто короткий (мін. {BRIEF_MIN_LEN} символів)"
        )
    if len(text) > BRIEF_MAX_LEN:
        text = text[:BRIEF_MAX_LEN]
    return text


def _prediction_text(output: Any) -> str:
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    if isinstance(output, list):
        return "".join(str(x) for x in output)
    return str(output)


def _absolute_media_url(file_field) -> str:
    url = file_field.url
    if url.startswith("http"):
        return url
    return f"{site_url()}{url}"


def _hero_block(image_url: str, alt: str = "mr.Carpet") -> str:
    src = html_lib.escape(image_url, quote=True)
    alt_esc = html_lib.escape(alt, quote=True)
    return (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">'
        '<tr><td align="center" style="padding:0 0 22px;">'
        f'<img src="{src}" alt="{alt_esc}" width="560" '
        'style="display:block;width:100%;max-width:560px;height:auto;'
        'border:0;border-radius:8px;" />'
        "</td></tr></table>"
    )


def _ensure_hero(body: str, hero_url: str | None) -> str:
    if not hero_url:
        return body or ""
    html = body or ""
    if hero_url in html or "/newsletter/heroes/" in html:
        return html
    return f"{_hero_block(hero_url)}\n{html}"


def _hero_filename(campaign_id: int) -> str:
    return f"campaign-{campaign_id}-hero.webp"


class ReplicateNewsletterService:
    def __init__(self):
        token = settings.REPLICATE_API_TOKEN
        if not token:
            raise NewsletterGenerationError(
                "REPLICATE_API_TOKEN не налаштовано. Додайте токен у .env"
            )
        self.client = replicate.Client(api_token=token)

    def generate_for_campaign(
        self, campaign: NewsletterCampaign
    ) -> NewsletterGenerationResult:
        brief = _normalize_brief(campaign.brief or campaign.subject)
        base = site_url()
        has_hero = bool(campaign.hero_image)
        user_prompt = (
            f"Сайт: {base}\n"
            f"Тема (якщо є): {campaign.subject or '—'}\n"
            f"Preheader (якщо є): {campaign.preheader or '—'}\n"
            f"Hero вже завантажено менеджером: {'так' if has_hero else 'ні'}\n"
        )
        if (campaign.image_prompt or "").strip():
            user_prompt += (
                f"Чернетка image_prompt (можна покращити): "
                f"{campaign.image_prompt.strip()}\n"
            )
        user_prompt += f"\nБриф менеджера:\n{brief}\n"

        campaign.status = NewsletterCampaign.STATUS_GENERATING
        campaign.ai_model = TEXT_MODEL
        campaign.ai_prompt_snapshot = f"{SYSTEM_PROMPT}\n\n---\n\n{user_prompt}"
        campaign.save(
            update_fields=[
                "status",
                "ai_model",
                "ai_prompt_snapshot",
                "updated_at",
            ]
        )

        t0 = time.monotonic()
        image_generated = False
        try:
            data = self._run_text_model(user_prompt)
            image_prompt = (data.get("image_prompt") or "").strip()
            if image_prompt:
                campaign.image_prompt = image_prompt[:2000]
                campaign.save(update_fields=["image_prompt", "updated_at"])

            if not campaign.hero_image:
                prompt_for_image = image_prompt or (campaign.image_prompt or "").strip()
                if not prompt_for_image:
                    prompt_for_image = (
                        "Photorealistic cozy living room with a premium textured area rug, "
                        "soft natural window light, warm beige tones, no logos, no text."
                    )
                raw = self._run_image(prompt_for_image)
                optimized = optimize_product_image(
                    raw,
                    max_width=IMAGE_MAX_WIDTH,
                    quality=IMAGE_WEBP_QUALITY,
                )
                campaign.hero_image.save(
                    _hero_filename(campaign.pk),
                    ContentFile(optimized),
                    save=True,
                )
                image_generated = True
                campaign.refresh_from_db()
        except Exception:
            campaign.status = NewsletterCampaign.STATUS_DRAFT
            campaign.save(update_fields=["status", "updated_at"])
            raise

        hero_url = None
        if campaign.hero_image:
            hero_url = _absolute_media_url(campaign.hero_image)

        body = _ensure_hero(data.get("body_html") or "", hero_url)
        body = sanitize_newsletter_html(body)
        if len(body) < 40:
            campaign.status = NewsletterCampaign.STATUS_DRAFT
            campaign.save(update_fields=["status", "updated_at"])
            raise NewsletterGenerationError("Модель повернула порожній HTML")

        subject = (data.get("subject") or "").strip() or campaign.subject
        preheader = (data.get("preheader") or "").strip()
        if not campaign.subject and subject:
            campaign.subject = subject[:255]
        if preheader and not campaign.preheader:
            campaign.preheader = preheader[:255]
        campaign.body_html = body
        campaign.status = NewsletterCampaign.STATUS_READY
        models = TEXT_MODEL if not image_generated else f"{TEXT_MODEL}+{IMAGE_MODEL}"
        campaign.ai_model = models
        campaign.save(
            update_fields=[
                "subject",
                "preheader",
                "body_html",
                "status",
                "ai_model",
                "updated_at",
            ]
        )
        duration = round(time.monotonic() - t0, 1)
        logger.info(
            "Newsletter campaign #%s generated model=%s image=%s duration=%.1fs",
            campaign.pk,
            models,
            image_generated,
            duration,
        )
        return NewsletterGenerationResult(
            campaign_id=campaign.pk,
            subject=campaign.subject,
            model=models,
            duration_sec=duration,
            image_generated=image_generated,
        )

    def _run_text_model(self, user_prompt: str) -> dict[str, Any]:
        prediction = self.client.predictions.create(
            model=TEXT_MODEL,
            input={
                "prompt": user_prompt,
                "system_prompt": SYSTEM_PROMPT,
                "temperature": 0.55,
                "max_completion_tokens": 4500,
            },
        )
        prediction = poll_prediction(
            prediction,
            timeout_sec=PREDICTION_TIMEOUT_SEC,
            poll_interval_sec=POLL_INTERVAL_SEC,
            error_cls=NewsletterGenerationError,
            label="newsletter-html",
        )
        if prediction.status != "succeeded":
            raise NewsletterGenerationError(
                f"Replicate failed: {prediction.status} {prediction.error}"
            )
        text = _prediction_text(prediction.output)
        return extract_json_object(text, error_cls=NewsletterGenerationError)

    def _run_image(self, image_prompt: str) -> bytes:
        prompt = (
            f"{image_prompt.strip()} "
            "Photorealistic interior photography, soft natural light, "
            "no logos, no watermarks, no readable text."
        )
        prediction = self.client.predictions.create(
            model=IMAGE_MODEL,
            input={
                "prompt": prompt,
                "aspect_ratio": IMAGE_ASPECT,
                "quality": IMAGE_QUALITY,
                "output_format": "webp",
                "output_compression": 85,
                "background": "opaque",
                "number_of_images": 1,
            },
        )
        logger.info("Newsletter hero prediction id=%s", prediction.id)
        prediction = poll_prediction(
            prediction,
            timeout_sec=IMAGE_TIMEOUT_SEC,
            poll_interval_sec=POLL_INTERVAL_SEC,
            error_cls=NewsletterGenerationError,
            label="newsletter-image",
        )
        if prediction.status != "succeeded":
            raise NewsletterGenerationError(
                prediction.error or "Помилка моделі зображення"
            )
        output = prediction.output
        if not output:
            raise NewsletterGenerationError("Replicate не повернув зображення")
        url = output[0] if isinstance(output, list) else output
        if not isinstance(url, str) or not url.startswith("http"):
            raise NewsletterGenerationError("Некоректний URL зображення від Replicate")
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        if not response.content:
            raise NewsletterGenerationError("Порожній файл hero-зображення")
        return response.content
