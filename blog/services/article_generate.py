"""Generate blog Article from a topic via Replicate (text + cheap cover)."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any

import replicate
import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.urls import reverse
from django.utils.text import slugify
from unidecode import unidecode

from blog.models import Article
from blog.services.html_sanitize import sanitize_article_html
from project.replicate_utils import extract_json_object, poll_prediction

logger = logging.getLogger("blog.article_generate")

TEXT_MODEL = "openai/gpt-4o-mini"
IMAGE_MODEL = "openai/gpt-image-2"
IMAGE_QUALITY = "low"  # cheaper than high/auto
IMAGE_ASPECT = "3:2"
# Per-step timeout (text OR image). Admin request is sync — keep under reverse-proxy limits.
PREDICTION_TIMEOUT_SEC = 120
POLL_INTERVAL_SEC = 2
TOPIC_MIN_LEN = 3
TOPIC_MAX_LEN = 300

SYSTEM_PROMPT = """Ти SEO/GEO-редактор блогу українського інтернет-магазину килимів mr.Carpet (Магазин Меблі Килими).

За темою користувача згенеруй статтю українською для блогу.

Правила:
- Пиши природною українською, без keyword soup і води.
- Не вигадуй конкретні ціни, SKU, наявність товарів і юридичні обіцянки.
- Структура description — HTML (без markdown, без <html>/<body>):
  1) перший <p> з <strong>Коротко:</strong> … (1–2 речення — відповідь для AI-цитати);
  2) 3–5 блоків <h2>питання/підтема</h2> + <p> + за потреби <ul>/<ol>/<li>;
  3) в кінці <p> з внутрішніми лінками: <a href="/catalog/">каталог</a>, <a href="/faq/">FAQ</a>, <a href="/delivery/">доставка і оплата</a>.
- Дозволені теги: p, h2, ul, ol, li, strong, em, a, br.
- title: 45–90 символів, без «| mr.Carpet».
- meta_title: 45–60 символів, SEO-варіант title.
- meta_description: 145–160 символів.
- meta_keys: 5–8 фраз через кому.
- image_prompt: АНГЛІЙСЬКОЮ, 1–2 речення для cover photo: interior/lifestyle with rug, photorealistic, no logos, no readable text, no watermarks, warm natural light.

Відповідь СТРОГО одним JSON без markdown:
{"title":"...","meta_title":"...","meta_description":"...","meta_keys":"...","description":"...","image_prompt":"..."}
"""


class ArticleGenerationError(Exception):
    """Replicate / validation error for blog article generation."""


@dataclass(frozen=True)
class ArticleGenerationResult:
    article_id: int
    title: str
    edit_url: str
    text_duration_sec: float
    image_duration_sec: float
    models: dict[str, str]


def _clean_str(value: Any, max_len: int | None = None) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if max_len is not None and len(text) > max_len:
        text = text[:max_len].rstrip()
    return text


def normalize_topic(topic: str) -> str:
    text = (topic or "").strip()
    if len(text) < TOPIC_MIN_LEN:
        raise ArticleGenerationError(
            f"Вкажіть тему (мінімум {TOPIC_MIN_LEN} символи)"
        )
    if len(text) > TOPIC_MAX_LEN:
        raise ArticleGenerationError(
            f"Тема занадто довга (макс. {TOPIC_MAX_LEN} символів)"
        )
    return text


def parse_article_payload(data: dict[str, Any]) -> dict[str, str]:
    title = _clean_str(data.get("title"), 200)
    # Don't collapse whitespace inside HTML before sanitize
    description = sanitize_article_html(str(data.get("description") or "").strip())
    meta_title = _clean_str(data.get("meta_title"), 120) or title[:60]
    meta_description = _clean_str(data.get("meta_description"), 180)
    meta_keys = _clean_str(data.get("meta_keys"), 300)
    image_prompt = _clean_str(data.get("image_prompt"), 800)

    for suffix in (" | mr.Carpet", " | mr.carpet", " — mr.Carpet", " - mr.Carpet"):
        if title.endswith(suffix):
            title = title[: -len(suffix)].strip()
        if meta_title.endswith(suffix):
            meta_title = meta_title[: -len(suffix)].strip()

    if len(title) < 8:
        raise ArticleGenerationError("Занадто короткий title")
    if len(description) < 80 or "<" not in description:
        raise ArticleGenerationError("description має бути HTML-статтею")
    if len(meta_description) < 80:
        raise ArticleGenerationError("meta_description занадто короткий")
    if len(image_prompt) < 20:
        raise ArticleGenerationError("image_prompt порожній")

    if len(meta_description) > 165:
        meta_description = meta_description[:160].rsplit(" ", 1)[0]

    return {
        "title": title,
        "description": description,
        "meta_title": meta_title,
        "meta_description": meta_description,
        "meta_keys": meta_keys,
        "image_prompt": image_prompt,
    }


def _cover_filename(title: str) -> str:
    base = slugify(unidecode(title or ""))[:80] or "article"
    return f"{base}.webp"


class ReplicateArticleService:
    def __init__(self):
        token = settings.REPLICATE_API_TOKEN
        if not token:
            raise ArticleGenerationError(
                "REPLICATE_API_TOKEN не налаштовано. Додайте токен у .env"
            )
        self.client = replicate.Client(api_token=token)

    def generate_and_create(self, topic: str) -> ArticleGenerationResult:
        topic = normalize_topic(topic)

        # 1–2) Paid Replicate work first — no DB row until both succeed
        t0 = time.monotonic()
        raw_text = self._run_text(topic)
        fields = parse_article_payload(
            extract_json_object(raw_text, error_cls=ArticleGenerationError)
        )
        text_duration = round(time.monotonic() - t0, 1)

        t1 = time.monotonic()
        image_bytes = self._run_image(fields["image_prompt"])
        image_duration = round(time.monotonic() - t1, 1)

        # 3) Persist once (text + cover together)
        with transaction.atomic():
            article = Article(
                title=fields["title"],
                description=fields["description"],
                meta_title=fields["meta_title"],
                meta_description=fields["meta_description"],
                meta_keys=fields["meta_keys"],
            )
            article.image.save(
                _cover_filename(fields["title"]),
                ContentFile(image_bytes),
                save=False,
            )
            article.save()

        edit_url = reverse("admin:blog_article_change", args=[article.pk])
        logger.info(
            "Article #%s created topic=%r text=%.1fs image=%.1fs",
            article.pk,
            topic[:80],
            text_duration,
            image_duration,
        )
        return ArticleGenerationResult(
            article_id=article.pk,
            title=article.title,
            edit_url=edit_url,
            text_duration_sec=text_duration,
            image_duration_sec=image_duration,
            models={
                "text": TEXT_MODEL,
                "image": IMAGE_MODEL,
                "image_quality": IMAGE_QUALITY,
            },
        )

    def _run_text(self, topic: str) -> str:
        prediction = self.client.predictions.create(
            model=TEXT_MODEL,
            input={
                "system_prompt": SYSTEM_PROMPT,
                "prompt": (
                    f"Тема статті:\n{topic}\n\n"
                    "Згенеруй JSON для блогу mr.Carpet."
                ),
                "temperature": 0.5,
                "max_completion_tokens": 2200,
            },
        )
        logger.info("Article text prediction id=%s", prediction.id)
        prediction = poll_prediction(
            prediction,
            timeout_sec=PREDICTION_TIMEOUT_SEC,
            poll_interval_sec=POLL_INTERVAL_SEC,
            error_cls=ArticleGenerationError,
            label="text",
        )

        if prediction.status != "succeeded":
            raise ArticleGenerationError(
                prediction.error or "Помилка текстової моделі"
            )

        output = prediction.output
        if isinstance(output, list):
            output = "".join(str(x) for x in output)
        text = str(output or "").strip()
        if not text:
            raise ArticleGenerationError("Порожній output текстової моделі")
        return text

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
        logger.info("Article image prediction id=%s", prediction.id)
        prediction = poll_prediction(
            prediction,
            timeout_sec=PREDICTION_TIMEOUT_SEC,
            poll_interval_sec=POLL_INTERVAL_SEC,
            error_cls=ArticleGenerationError,
            label="image",
        )

        if prediction.status != "succeeded":
            raise ArticleGenerationError(
                prediction.error or "Помилка моделі зображення"
            )

        output = prediction.output
        if not output:
            raise ArticleGenerationError("Replicate не повернув зображення")
        url = output[0] if isinstance(output, list) else output
        if not isinstance(url, str) or not url.startswith("http"):
            raise ArticleGenerationError("Некоректний URL зображення від Replicate")

        response = requests.get(url, timeout=60)
        response.raise_for_status()
        if not response.content:
            raise ArticleGenerationError("Порожній файл обкладинки")
        return response.content
