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
from project.replicate_utils import extract_json_object
from project.text_encoding import fix_utf8_mojibake

logger = logging.getLogger("catalog.seo_generate")

MODEL = "openai/gpt-4o-mini"
PREDICTION_TIMEOUT_SEC = 120
POLL_INTERVAL_SEC = 2
BATCH_PAUSE_SEC = 0.75

SYSTEM_PROMPT = """Ти SEO-копірайтер українського інтернет-магазину килимів mr.Carpet (Магазин Меблі Килими).

Завдання: за фото килима + даними товару згенерувати тексти українською.

Правила:
- Пиши природною українською, без keyword soup і без води.
- Не вигадуй матеріал, країну, склад, бренд виробника, якщо цього немає в PRODUCT DATA.
- З фото можна брати: колір, орнамент/стиль, візуальну форму (круглий/прямокутний тощо), загальне враження.
- Використовуй specs/categories/size з PRODUCT DATA, якщо вони є (форма, склад, виробник, «в дитячу» тощо).

meta_title:
- 45–60 символів.
- НЕ копіюй title 1-в-1. Зроби SEO-варіант: товар + 1–2 атрибути (форма/колір/кімната/мотив з фото).
- БЕЗ суфікса «| mr.Carpet», БЕЗ «купити» на початку.

meta_description:
- ОБОВ'ЯЗКОВО 145–160 символів (порахуй). Якщо коротше 145 — ДОПИШИ до діапазону.
- Структура: що за килим → для кого/куди → 1 факт зі specs (склад/виробник/розмір) → доставка по Україні.
- Без keyword soup.

meta_keys:
- 5–8 слів/фраз через кому; можна порожній рядок.

description (PDP):
- 1–2 короткі речення. Лише щоб зрозуміти, що за килим.
- Без характеристик «на око», без довгих списків переваг, без ціни.

Відповідь СТРОГО одним JSON-об'єктом без markdown і без коментарів:
{"meta_title":"...","meta_description":"...","meta_keys":"...","description":"..."}
"""


class SeoGenerationError(Exception):
    """Replicate / validation error for SEO generation."""


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
        "is_new": bool(product.is_novelty),
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
        "На фото — саме цей килим.\n"
        "Перевір довжину meta_description: має бути 145–160 символів.\n"
        "meta_title не копіюй з title один-в-один.\n"
        "Згенеруй JSON."
    )


def _extract_json_object(text: str) -> dict[str, Any]:
    return extract_json_object(text, error_cls=SeoGenerationError)


def _clean_field(value: Any, *, max_len: int | None = None) -> str:
    text = fix_utf8_mojibake(re.sub(r"\s+", " ", str(value or "")).strip())
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


def apply_seo_to_product(product: Product, result: SeoGenerationResult) -> list[str]:
    """Persist SEO fields; description only when empty. Returns updated field names."""
    update_fields = ["meta_title", "meta_description", "meta_keys"]
    product.meta_title = result.meta_title
    product.meta_description = result.meta_description
    product.meta_keys = result.meta_keys
    if result.fill_description and not (product.description or "").strip():
        product.description = result.description
        update_fields.append("description")
    product.save(update_fields=update_fields)
    return update_fields


def generate_seo_for_products(product_ids: list[int]) -> dict[str, Any]:
    """
    Sequential batch: one Replicate call at a time (no parallel flood).
    Continues on per-product errors.
    """
    ok: list[int] = []
    failed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    service = ReplicateSeoService()
    total = len(product_ids)

    for index, product_id in enumerate(product_ids, start=1):
        try:
            product = Product.admin_objects.get(pk=int(product_id))
        except (Product.DoesNotExist, TypeError, ValueError):
            skipped.append({"product_id": product_id, "error": "not found"})
            continue

        if not product.image:
            skipped.append({"product_id": product.pk, "error": "no image"})
            continue

        try:
            logger.info("SEO batch %s/%s: product #%s", index, total, product.pk)
            result = service.generate_for_product(product)
            apply_seo_to_product(product, result)
            ok.append(product.pk)
        except Exception as exc:
            logger.exception("SEO batch failed for product #%s", product.pk)
            failed.append({"product_id": product.pk, "error": str(exc)[:500]})

        if index < total:
            time.sleep(BATCH_PAUSE_SEC)

    return {
        "success": True,
        "ok": ok,
        "failed": failed,
        "skipped": skipped,
        "ok_count": len(ok),
        "failed_count": len(failed),
        "skipped_count": len(skipped),
    }


class ReplicateSeoService:
    def __init__(self):
        token = settings.REPLICATE_API_TOKEN
        if not token:
            raise SeoGenerationError(
                "REPLICATE_API_TOKEN не налаштовано. Додайте токен у .env"
            )
        self.client = replicate.Client(api_token=token)

    def generate_for_product(self, product: Product) -> SeoGenerationResult:
        context = collect_product_context(product)
        fill_description = bool(context["need_description"])
        image_bytes, image_name = resolve_product_image_bytes(product)
        prompt = build_user_prompt(context)

        started = time.monotonic()
        raw_text = self._run(image_bytes, image_name, prompt)
        data = _extract_json_object(raw_text)
        fields = parse_seo_payload(data, fill_description=fill_description)
        duration = round(time.monotonic() - started, 1)

        logger.info(
            "SEO ok product #%s title_len=%s desc_len=%s (%.1fs)",
            product.pk,
            len(fields["meta_title"]),
            len(fields["meta_description"]),
            duration,
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
        )

    def _run(self, image_bytes: bytes, image_name: str, prompt: str) -> str:
        file_obj = io.BytesIO(image_bytes)
        file_obj.name = image_name

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
        logger.info("SEO prediction id=%s", prediction.id)
        prediction = self._poll(prediction)

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
        while prediction.status in ("starting", "processing"):
            if time.monotonic() > deadline:
                raise SeoGenerationError("Таймаут очікування Replicate")
            time.sleep(POLL_INTERVAL_SEC)
            prediction.reload()
        return prediction
