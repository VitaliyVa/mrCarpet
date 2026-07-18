"""Generate email-safe inner HTML for NewsletterCampaign via Replicate."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import replicate
from django.conf import settings

from project.email_branding import site_url
from project.models import NewsletterCampaign
from project.replicate_utils import extract_json_object, poll_prediction
from project.services.newsletter_html_sanitize import sanitize_newsletter_html

logger = logging.getLogger(__name__)

TEXT_MODEL = "openai/gpt-4o-mini"
PREDICTION_TIMEOUT_SEC = 120
POLL_INTERVAL_SEC = 2
BRIEF_MIN_LEN = 10
BRIEF_MAX_LEN = 4000

SYSTEM_PROMPT = """Ти email-верстальник для українського магазину килимів mr.Carpet.

Завдання: з брифу менеджера зібрати INNER HTML тіла листа (не повний документ).

Критичні правила (поштовики: Gmail, Outlook, Apple Mail):
1. ТІЛЬКИ table[role=presentation], tr, td, p, span, strong, a, br, img, ul/ol/li.
2. Без <!DOCTYPE>, <html>, <head>, <body>, <style>, script, iframe, flex, grid, position.
3. Усі стилі — INLINE (style="..."). Шрифт: Arial, Helvetica, sans-serif.
4. Кольори бренду: текст #453f3a, акцент/CTA bgcolor #a46c46, текст на CTA #fffcf2, фон контенту #fffcf2.
5. Посилання абсолютні https://… CTA — table-кнопка (td bgcolor + <a>), не <button>.
6. Зображення лише якщо в брифі є реальний https URL; інакше без img. width/height + style="display:block;border:0;".
7. В кінці ОБОВʼЯЗКОВО лінк: <a href="{{unsubscribe_url}}">Відписатися від розсилки</a>
   Плейсхолдер саме {{unsubscribe_url}} (буквально).
8. Українською. Не вигадуй ціни/знижки/дати, яких немає в брифі.
9. Зовнішній header з логотипом НЕ роби — він уже в шаблоні сайту.

Відповідь СТРОГО одним JSON:
{"subject":"...","preheader":"...","body_html":"<table role=\\"presentation\\"...>...</table>"}
"""


class NewsletterGenerationError(Exception):
    pass


@dataclass(frozen=True)
class NewsletterGenerationResult:
    campaign_id: int
    subject: str
    model: str
    duration_sec: float


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
        user_prompt = (
            f"Сайт: {base}\n"
            f"Тема (якщо є): {campaign.subject or '—'}\n"
            f"Preheader (якщо є): {campaign.preheader or '—'}\n\n"
            f"Бриф менеджера:\n{brief}\n"
        )

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
        try:
            data = self._run_model(user_prompt)
        except Exception:
            campaign.status = NewsletterCampaign.STATUS_DRAFT
            campaign.save(update_fields=["status", "updated_at"])
            raise

        body = sanitize_newsletter_html(data.get("body_html") or "")
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
        campaign.save(
            update_fields=[
                "subject",
                "preheader",
                "body_html",
                "status",
                "updated_at",
            ]
        )
        duration = round(time.monotonic() - t0, 1)
        logger.info(
            "Newsletter campaign #%s HTML generated model=%s duration=%.1fs",
            campaign.pk,
            TEXT_MODEL,
            duration,
        )
        return NewsletterGenerationResult(
            campaign_id=campaign.pk,
            subject=campaign.subject,
            model=TEXT_MODEL,
            duration_sec=duration,
        )

    def _run_model(self, user_prompt: str) -> dict[str, Any]:
        prediction = self.client.predictions.create(
            model=TEXT_MODEL,
            input={
                "prompt": user_prompt,
                "system_prompt": SYSTEM_PROMPT,
                "temperature": 0.4,
                "max_completion_tokens": 3500,
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
        data = extract_json_object(text, error_cls=NewsletterGenerationError)
        return data
