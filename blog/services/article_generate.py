"""Generate blog Article from a topic via Replicate (2× text + cheap cover)."""

from __future__ import annotations

import json
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
from django.utils.html import strip_tags
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
# Per-step timeout. Admin request is sync (structure + expand + image).
PREDICTION_TIMEOUT_SEC = 120
POLL_INTERVAL_SEC = 2
TOPIC_MIN_LEN = 3
TOPIC_MAX_LEN = 300
MIN_BODY_PLAIN_CHARS = 1400  # after strip_tags — forces real article length

SYSTEM_PROMPT_STRUCTURE = """Ти SEO/GEO-редактор блогу українського інтернет-магазину килимів mr.Carpet.

Завдання: за темою зібрати КАРКАС статті (без повного HTML-тіла).

Правила:
- Українською, без keyword soup.
- Не вигадуй ціни, SKU, наявність, юридичні обіцянки.
- title = майбутній H1 (45–90 символів), без «| mr.Carpet».
- meta_title (45–60) — той самий інтент, що title (не міняй «як вибрати X» на «вибір X»).
- meta_description 145–160 символів.
- meta_keys: 5–8 фраз через кому.
- korotko: 1–2 конкретні речення-відповідь на тему (практичне правило, не «це важливо»).
- h2_questions: рівно 4 або 5 рядків; КОЖЕН — питання з «?»; без імперативів («Виміряйте…»).
- image_prompt: АНГЛІЙСЬКОЮ, 1–2 речення, photorealistic interior with rug, no logos/text/watermarks.

Відповідь СТРОГО одним JSON:
{"title":"...","meta_title":"...","meta_description":"...","meta_keys":"...","korotko":"...","h2_questions":["...?","...?","...?","...?"],"image_prompt":"..."}
"""

SYSTEM_PROMPT_EXPAND = """Ти SEO/GEO-редактор блогу mr.Carpet. Розгорни каркас у ПОВНИЙ HTML-текст статті.

Критично:
- H1 НЕ пиши (title уже є в шаблоні).
- Використовуй ТОЧНІ рядки з h2_questions як <h2>…</h2> (той самий текст, з «?»).
- Не додавай і не прибирай H2.
- Не використовуй markdown (# ##) і не <h1>/<h3>.
- Дозволені теги: p, h2, ul, ol, li, strong, em, a, br.
- Українською, конкретно, без води і keyword soup.
- Не вигадуй ціни/SKU/наявність.

Обсяг (обов'язково багато тексту):
- Після <strong>Коротко:</strong> — візьми korotko (можна трохи уточнити, 1–2 речення).
- Під КОЖНИМ <h2>: спочатку 1 речення-відповідь, далі ще 2–3 <p> з деталями/прикладами; у 1–2 секціях додай <ul> або <ol> (3–5 пунктів).
- Ціль: сумарно ≥1500 символів видимого тексту (без тегів). Краще 2000–3500.

Фінал:
- останній <p> з лінками:
  <a href="/catalog/">каталог килимів</a>, <a href="/faq/">часті питання</a>, <a href="/delivery/">доставка і оплата</a>.

Відповідь СТРОГО одним JSON:
{"description":"<p><strong>Коротко:</strong> ...</p><h2>...</h2><p>...</p>..."}
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


def _h2_texts(html: str) -> list[str]:
    return [
        re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", t)).strip()
        for t in re.findall(r"<h2[^>]*>(.*?)</h2>", html or "", flags=re.I | re.S)
    ]


def _strip_brand_suffix(text: str) -> str:
    for suffix in (" | mr.Carpet", " | mr.carpet", " — mr.Carpet", " - mr.Carpet"):
        if text.endswith(suffix):
            return text[: -len(suffix)].strip()
    return text


def parse_structure_payload(data: dict[str, Any]) -> dict[str, Any]:
    title = _strip_brand_suffix(_clean_str(data.get("title"), 200))
    meta_title = _strip_brand_suffix(
        _clean_str(data.get("meta_title"), 120) or title[:60]
    )
    meta_description = _clean_str(data.get("meta_description"), 180)
    meta_keys = _clean_str(data.get("meta_keys"), 300)
    korotko = _clean_str(data.get("korotko"), 400)
    image_prompt = _clean_str(data.get("image_prompt"), 800)
    raw_q = data.get("h2_questions")

    if len(title) < 8:
        raise ArticleGenerationError("Занадто короткий title")
    if len(meta_description) < 80:
        raise ArticleGenerationError("meta_description занадто короткий")
    if len(korotko) < 40:
        raise ArticleGenerationError("korotko занадто короткий")
    if len(image_prompt) < 20:
        raise ArticleGenerationError("image_prompt порожній")
    if not isinstance(raw_q, list) or not (4 <= len(raw_q) <= 5):
        raise ArticleGenerationError("h2_questions: потрібно 4–5 питань")

    questions: list[str] = []
    for item in raw_q:
        q = _clean_str(item, 140)
        if len(q) < 8:
            raise ArticleGenerationError("Порожнє питання в h2_questions")
        if "?" not in q and "？" not in q:
            raise ArticleGenerationError(f"H2 має бути питанням з «?»: {q}")
        questions.append(q)

    if len(meta_description) > 165:
        meta_description = meta_description[:160].rsplit(" ", 1)[0]

    return {
        "title": title,
        "meta_title": meta_title,
        "meta_description": meta_description,
        "meta_keys": meta_keys,
        "korotko": korotko,
        "h2_questions": questions,
        "image_prompt": image_prompt,
    }


def parse_expand_payload(
    data: dict[str, Any], *, structure: dict[str, Any]
) -> str:
    description = sanitize_article_html(str(data.get("description") or "").strip())
    if len(description) < 200 or "<" not in description:
        raise ArticleGenerationError("description має бути HTML-статтею")
    if re.search(r"<h1\b", description, re.I):
        raise ArticleGenerationError("У тексті статті не має бути <h1>")

    expected = structure["h2_questions"]
    actual = _h2_texts(description)
    if len(actual) != len(expected):
        raise ArticleGenerationError(
            f"Очікувалось {len(expected)} <h2>, отримано {len(actual)}"
        )
    for want, got in zip(expected, actual):
        if want.casefold() != got.casefold():
            raise ArticleGenerationError(
                f"H2 змінено (має бути точно з каркасу): «{want}» ≠ «{got}»"
            )

    plain = re.sub(r"\s+", " ", strip_tags(description)).strip()
    if len(plain) < MIN_BODY_PLAIN_CHARS:
        raise ArticleGenerationError(
            f"Текст занадто короткий ({len(plain)} символів, "
            f"мінімум {MIN_BODY_PLAIN_CHARS}). Перегенеруйте."
        )
    if not (
        re.search(r"<strong>\s*Коротко:\s*</strong>", description, re.I)
        or plain.lower().startswith("коротко:")
    ):
        raise ArticleGenerationError("Немає блоку «Коротко:» на початку")

    return description


def parse_article_payload(data: dict[str, Any]) -> dict[str, str]:
    """Backward-compatible single-shot parser (tests / fallback)."""
    title = _strip_brand_suffix(_clean_str(data.get("title"), 200))
    description = sanitize_article_html(str(data.get("description") or "").strip())
    meta_title = _strip_brand_suffix(
        _clean_str(data.get("meta_title"), 120) or title[:60]
    )
    meta_description = _clean_str(data.get("meta_description"), 180)
    meta_keys = _clean_str(data.get("meta_keys"), 300)
    image_prompt = _clean_str(data.get("image_prompt"), 800)

    if len(title) < 8:
        raise ArticleGenerationError("Занадто короткий title")
    if len(description) < 80 or "<" not in description:
        raise ArticleGenerationError("description має бути HTML-статтею")
    if len(meta_description) < 80:
        raise ArticleGenerationError("meta_description занадто короткий")
    if len(image_prompt) < 20:
        raise ArticleGenerationError("image_prompt порожній")
    if re.search(r"<h1\b", description, re.I):
        raise ArticleGenerationError("У тексті статті не має бути <h1> (H1 лише з title)")

    h2s = _h2_texts(description)
    if len(h2s) < 3:
        raise ArticleGenerationError("Потрібно мінімум 3 секції <h2>")
    non_questions = [h for h in h2s if "?" not in h and "？" not in h]
    if len(non_questions) > len(h2s) // 2:
        raise ArticleGenerationError(
            "Більшість <h2> мають бути питаннями з «?» "
            f"(зараз без «?»: {', '.join(non_questions[:3])})"
        )

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

        # Text pass 1+2, then image — no DB row until all succeed
        t0 = time.monotonic()
        structure = self._run_text_structure(topic)
        description = self._run_text_expand(topic, structure)
        text_duration = round(time.monotonic() - t0, 1)

        fields = {
            "title": structure["title"],
            "description": description,
            "meta_title": structure["meta_title"],
            "meta_description": structure["meta_description"],
            "meta_keys": structure["meta_keys"],
            "image_prompt": structure["image_prompt"],
        }

        t1 = time.monotonic()
        image_bytes = self._run_image(fields["image_prompt"])
        image_duration = round(time.monotonic() - t1, 1)

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
            "Article #%s created topic=%r text=%.1fs image=%.1fs plain_chars=%s",
            article.pk,
            topic[:80],
            text_duration,
            image_duration,
            len(strip_tags(description)),
        )
        return ArticleGenerationResult(
            article_id=article.pk,
            title=article.title,
            edit_url=edit_url,
            text_duration_sec=text_duration,
            image_duration_sec=image_duration,
            models={
                "text": TEXT_MODEL,
                "text_passes": "2",
                "image": IMAGE_MODEL,
                "image_quality": IMAGE_QUALITY,
            },
        )

    def _run_text_structure(self, topic: str) -> dict[str, Any]:
        raw = self._predict_text(
            system=SYSTEM_PROMPT_STRUCTURE,
            prompt=(
                f"Тема статті:\n{topic}\n\n"
                "Згенеруй JSON-каркас (title/meta/korotko/h2_questions/image_prompt)."
            ),
            max_tokens=900,
            temperature=0.45,
            label="text-structure",
        )
        return parse_structure_payload(
            extract_json_object(raw, error_cls=ArticleGenerationError)
        )

    def _run_text_expand(self, topic: str, structure: dict[str, Any]) -> str:
        skeleton = {
            "topic": topic,
            "title": structure["title"],
            "korotko": structure["korotko"],
            "h2_questions": structure["h2_questions"],
        }
        raw = self._predict_text(
            system=SYSTEM_PROMPT_EXPAND,
            prompt=(
                "КАРКАС (JSON):\n"
                f"{json.dumps(skeleton, ensure_ascii=False, indent=2)}\n\n"
                "Розгорни у повний HTML description (≥1500 символів видимого тексту)."
            ),
            max_tokens=4500,
            temperature=0.55,
            label="text-expand",
        )
        data = extract_json_object(raw, error_cls=ArticleGenerationError)
        return parse_expand_payload(data, structure=structure)

    def _predict_text(
        self,
        *,
        system: str,
        prompt: str,
        max_tokens: int,
        temperature: float,
        label: str,
    ) -> str:
        prediction = self.client.predictions.create(
            model=TEXT_MODEL,
            input={
                "system_prompt": system,
                "prompt": prompt,
                "temperature": temperature,
                "max_completion_tokens": max_tokens,
            },
        )
        logger.info("Article %s prediction id=%s", label, prediction.id)
        prediction = poll_prediction(
            prediction,
            timeout_sec=PREDICTION_TIMEOUT_SEC,
            poll_interval_sec=POLL_INTERVAL_SEC,
            error_cls=ArticleGenerationError,
            label=label,
        )
        if prediction.status != "succeeded":
            raise ArticleGenerationError(
                prediction.error or f"Помилка моделі ({label})"
            )
        output = prediction.output
        if isinstance(output, list):
            output = "".join(str(x) for x in output)
        text = str(output or "").strip()
        if not text:
            raise ArticleGenerationError(f"Порожній output ({label})")
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
