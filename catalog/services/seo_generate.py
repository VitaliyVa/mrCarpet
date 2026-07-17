"""Generate product SEO + short PDP description via Replicate openai/gpt-4o-mini."""

from __future__ import annotations

import io
import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import replicate
from django.conf import settings

from catalog.models import Product
from catalog.services.scene_size import get_first_product_size_label

logger = logging.getLogger("catalog.seo_generate")

MODEL = "openai/gpt-4o-mini"
PREDICTION_TIMEOUT_SEC = 120
POLL_INTERVAL_SEC = 2

SYSTEM_PROMPT = """Ти SEO-копірайтер українського інтернет-магазину килимів mr.Carpet (Магазин Меблі Килими).

Завдання: за фото килима + даними товару згенерувати тексти українською.

Правила:
- Пиши природною українською, без keyword soup і без води.
- Не вигадуй матеріал, країну, склад, бренд виробника, якщо цього немає в PRODUCT DATA.
- З фото можна брати: колір, орнамент/стиль, візуальну форму (круглий/прямокутний тощо), загальне враження.
- meta_title: до ~60 символів, БЕЗ суфікса «| mr.Carpet» і без слова «купити» на початку.
- meta_description: 145–160 символів, як коротка відповідь на інтент покупця (що це, для кого/куди, доставка по Україні — якщо доречно).
- meta_keys: 5–8 слів/фраз через кому, опційно; можна порожній рядок.
- description: 1–2 короткі речення для картки товару (PDP). Лише щоб зрозуміти, що за килим. Без характеристик «на око», без довгих списків переваг.
- Відповідь СТРОГО одним JSON-об'єктом без markdown і без коментарів:
{"meta_title":"...","meta_description":"...","meta_keys":"...","description":"..."}
"""


class SeoGenerationError(Exception):
    """Replicate / validation error for SEO generation."""

    def __init__(self, message: str, logs: list[dict] | None = None):
        super().__init__(message)
        self.logs = logs or []


class SeoJobLog:
    def __init__(self):
        self.entries: list[dict] = []

    def _add(self, level: str, message: str) -> None:
        self.entries.append({"level": level, "text": message})
        if level == "error":
            logger.error(message)
        else:
            logger.info(message)

    def info(self, message: str) -> None:
        self._add("info", message)

    def ok(self, message: str) -> None:
        self._add("ok", message)

    def error(self, message: str) -> None:
        self._add("error", message)


@dataclass(frozen=True)
class SeoGenerationResult:
    meta_title: str
    meta_description: str
    meta_keys: str
    description: str
    model: str
    duration_sec: float
    fill_description: bool
    raw_text: str
    logs: list[dict]


def collect_product_context(product: Product) -> dict[str, Any]:
    """Gather product facts for the prompt (mirrors scene-size idea, but fuller)."""
    sizes: list[dict[str, Any]] = []
    for attr in (
        product.product_attr.select_related("size")
        .prefetch_related("width")
        .order_by("sort_order", "pk")
    ):
        size_title = (attr.size.title if attr.size else "") or ""
        widths = [str(w.width) for w in attr.width.all()] if attr.custom_attribute else []
        sizes.append(
            {
                "size": size_title or None,
                "price": attr.custom_price if attr.custom_attribute else attr.price,
                "discount_percent": attr.discount,
                "quantity": attr.quantity,
                "custom": bool(attr.custom_attribute),
                "custom_width_m": widths or None,
                "custom_len_m": (
                    f"{attr.min_len}–{attr.max_len}"
                    if attr.custom_attribute and attr.min_len is not None
                    else None
                ),
            }
        )

    primary_size = get_first_product_size_label(product)

    specs = []
    for row in product.product_specs.select_related("specification", "spec_value").all():
        if not row.specification or not row.spec_value:
            continue
        specs.append(
            {
                "name": row.specification.title,
                "value": row.spec_value.title,
            }
        )

    color_variants = []
    if product.color_group_id:
        for variant in (
            Product.admin_objects.filter(color_group_id=product.color_group_id)
            .select_related("active_color")
            .order_by("pk")
        ):
            color_variants.append(
                {
                    "product_id": variant.pk,
                    "title": variant.title,
                    "color": (
                        variant.active_color.title
                        if variant.active_color_id
                        else None
                    ),
                    "is_current": variant.pk == product.pk,
                }
            )

    categories = list(product.categories.values_list("title", flat=True))

    return {
        "product_id": product.pk,
        "title": product.title or "",
        "existing_description": (product.description or "").strip(),
        "categories": categories,
        "is_new": bool(product.is_new),
        "has_discount": bool(product.has_discount),
        "active_color": (
            product.active_color.title if product.active_color_id else None
        ),
        "color_variants": color_variants,
        "primary_size": primary_size,
        "sizes": sizes,
        "specifications": specs,
        "need_description": not bool((product.description or "").strip()),
    }


def build_user_prompt(context: dict[str, Any]) -> str:
    need_desc = context.get("need_description", True)
    desc_note = (
        "Поле description ЗАРАЗ ПОРОЖНЄ — обов'язково згенеруй короткий description."
        if need_desc
        else "Поле description уже заповнене — все одно поверни короткий description у JSON "
        "(адмінка вирішить, чи підставляти)."
    )
    payload = json.dumps(context, ensure_ascii=False, indent=2)
    return (
        "PRODUCT DATA (JSON):\n"
        f"{payload}\n\n"
        f"{desc_note}\n"
        "На фото — саме цей килим. Згенеруй JSON."
    )


def _extract_json_object(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise SeoGenerationError("Порожня відповідь моделі")

    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw, re.I)
    if fence:
        raw = fence.group(1).strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            raise SeoGenerationError("Не вдалося розпарсити JSON з відповіді моделі")
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise SeoGenerationError("Невалідний JSON у відповіді моделі") from exc

    if not isinstance(data, dict):
        raise SeoGenerationError("Очікувався JSON-об'єкт")
    return data


def _clean_field(value: Any, *, max_len: int | None = None) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if max_len and len(text) > max_len:
        text = text[: max_len - 1].rstrip() + "…"
    return text


def parse_seo_payload(data: dict[str, Any], *, fill_description: bool) -> dict[str, str]:
    meta_title = _clean_field(data.get("meta_title"), max_len=70)
    meta_description = _clean_field(data.get("meta_description"), max_len=180)
    meta_keys = _clean_field(data.get("meta_keys"), max_len=200)
    description = _clean_field(data.get("description"), max_len=400)

    if not meta_title:
        raise SeoGenerationError("Модель не повернула meta_title")
    if not meta_description:
        raise SeoGenerationError("Модель не повернула meta_description")
    if fill_description and not description:
        raise SeoGenerationError("Модель не повернула description")

    # Strip brand suffix if model ignored instructions
    for suffix in (" | mr.Carpet", " | mr.carpet", " — mr.Carpet", " - mr.Carpet"):
        if meta_title.endswith(suffix):
            meta_title = meta_title[: -len(suffix)].strip()

    return {
        "meta_title": meta_title,
        "meta_description": meta_description,
        "meta_keys": meta_keys,
        "description": description,
    }


def resolve_product_image_bytes(product: Product) -> tuple[bytes, str]:
    if not product.image:
        raise SeoGenerationError("Немає каталожного зображення товару")
    try:
        path = Path(product.image.path)
    except (ValueError, NotImplementedError) as exc:
        raise SeoGenerationError("Не вдалося прочитати файл зображення") from exc
    if not path.is_file():
        raise SeoGenerationError("Файл каталожного зображення не знайдено на диску")
    name = path.name or "product.jpg"
    return path.read_bytes(), name


class ReplicateSeoService:
    def __init__(self):
        token = settings.REPLICATE_API_TOKEN
        if not token:
            raise SeoGenerationError(
                "REPLICATE_API_TOKEN не налаштовано. Додайте токен у .env"
            )
        self.client = replicate.Client(api_token=token)
        self.job_log = SeoJobLog()

    def generate_for_product(self, product: Product) -> SeoGenerationResult:
        self.job_log.info(f"Товар #{product.pk} «{product.title}»")
        self.job_log.info(f"Модель: {MODEL}")

        context = collect_product_context(product)
        fill_description = bool(context["need_description"])
        self.job_log.info(
            "Контекст: "
            f"categories={context.get('categories')}, "
            f"primary_size={context.get('primary_size')!r}, "
            f"sizes={len(context.get('sizes') or [])}, "
            f"specs={len(context.get('specifications') or [])}, "
            f"active_color={context.get('active_color')!r}, "
            f"color_variants={len(context.get('color_variants') or [])}, "
            f"need_description={fill_description}"
        )
        self.job_log.info(
            "PRODUCT DATA JSON:\n"
            + json.dumps(context, ensure_ascii=False, indent=2)
        )

        try:
            image_bytes, image_name = resolve_product_image_bytes(product)
        except SeoGenerationError as exc:
            self.job_log.error(str(exc))
            raise SeoGenerationError(str(exc), logs=self.job_log.entries) from exc

        self.job_log.info(
            f"Фото: {image_name} ({len(image_bytes)} bytes, "
            f"path={getattr(product.image, 'name', '')})"
        )

        prompt = build_user_prompt(context)
        self.job_log.info(f"User prompt ({len(prompt)} chars):\n{prompt}")
        self.job_log.info(
            f"System prompt ({len(SYSTEM_PROMPT)} chars) — SEO rules + JSON schema"
        )

        started = time.monotonic()
        try:
            raw_text = self._run(image_bytes, image_name, prompt)
        except SeoGenerationError as exc:
            self.job_log.error(str(exc))
            raise SeoGenerationError(str(exc), logs=self.job_log.entries) from exc

        self.job_log.info(f"Raw model output ({len(raw_text)} chars):\n{raw_text}")

        try:
            data = _extract_json_object(raw_text)
            fields = parse_seo_payload(data, fill_description=fill_description)
        except SeoGenerationError as exc:
            self.job_log.error(str(exc))
            raise SeoGenerationError(str(exc), logs=self.job_log.entries) from exc

        duration = round(time.monotonic() - started, 1)
        self.job_log.ok(
            f"Parsed: title={fields['meta_title']!r} "
            f"({len(fields['meta_title'])} chars); "
            f"meta_desc={len(fields['meta_description'])} chars; "
            f"keys={fields['meta_keys']!r}; "
            f"description={fields['description']!r}; "
            f"fill_description={fill_description}; "
            f"{duration}s"
        )

        return SeoGenerationResult(
            meta_title=fields["meta_title"],
            meta_description=fields["meta_description"],
            meta_keys=fields["meta_keys"],
            description=fields["description"],
            model=MODEL,
            duration_sec=duration,
            fill_description=fill_description,
            raw_text=raw_text,
            logs=list(self.job_log.entries),
        )

    def _run(self, image_bytes: bytes, image_name: str, prompt: str) -> str:
        file_obj = io.BytesIO(image_bytes)
        file_obj.name = image_name

        self.job_log.info("Відправляю prediction на Replicate…")
        prediction = self.client.predictions.create(
            model=MODEL,
            input={
                "system_prompt": SYSTEM_PROMPT,
                "prompt": prompt,
                "image_input": [file_obj],
                "temperature": 0.4,
                "max_completion_tokens": 700,
            },
        )
        self.job_log.info(f"prediction id={prediction.id}, status={prediction.status}")
        logger.info("SEO: prediction id=%s", prediction.id)
        prediction = self._poll(prediction)
        self.job_log.info(f"prediction finished: status={prediction.status}")

        if prediction.status != "succeeded":
            error = prediction.error or "Невідома помилка Replicate"
            raise SeoGenerationError(error)

        output = prediction.output
        if isinstance(output, list):
            output = "".join(str(x) for x in output)
        text = str(output or "").strip()
        if not text:
            raise SeoGenerationError("Порожній output від моделі")
        return text

    def _poll(self, prediction):
        deadline = time.monotonic() + PREDICTION_TIMEOUT_SEC
        last_status = prediction.status
        while prediction.status in ("starting", "processing"):
            if time.monotonic() > deadline:
                raise SeoGenerationError("Таймаут очікування Replicate")
            time.sleep(POLL_INTERVAL_SEC)
            prediction.reload()
            if prediction.status != last_status:
                self.job_log.info(f"poll… status={prediction.status}")
                last_status = prediction.status
        return prediction
