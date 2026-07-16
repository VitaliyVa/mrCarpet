"""Filesystem cache for per-size carpet GLB files."""

from __future__ import annotations

import logging
import shutil
from decimal import Decimal
from pathlib import Path

from django.conf import settings

from catalog.services.make_glb import build_carpet_glb
from catalog.services.parse_size import SizeParseError, normalize_size_key, parse_size_label

logger = logging.getLogger("catalog.ar")


def _glb_root() -> Path:
    root = Path(settings.MEDIA_ROOT) / "ar" / "glb"
    root.mkdir(parents=True, exist_ok=True)
    return root


def product_glb_dir(product_id: int) -> Path:
    path = _glb_root() / str(product_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def glb_path_for(product_id: int, width: Decimal | float, length: Decimal | float) -> Path:
    key = normalize_size_key(width, length)
    return product_glb_dir(product_id) / f"{key}.glb"


def clear_product_glb_cache(product_id: int) -> None:
    path = _glb_root() / str(product_id)
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def get_or_build_glb(product, width: Decimal | float, length: Decimal | float) -> Path:
    """Return path to GLB, building from ar_texture if missing."""
    from catalog.models import Product

    if product.ar_status != Product.AR_STATUS_READY or not product.ar_texture:
        raise FileNotFoundError("AR-текстура не готова")

    path = glb_path_for(product.pk, width, length)
    if path.exists() and path.stat().st_size > 0:
        return path

    with product.ar_texture.open("rb") as src:
        texture_bytes = src.read()
    glb_bytes = build_carpet_glb(texture_bytes, float(width), float(length), alpha_mode="auto")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(glb_bytes)
    logger.info("GLB built product=%s size=%sx%s (%s KB)", product.pk, width, length, len(glb_bytes) // 1024)
    return path


def collect_fixed_sizes(product) -> list[tuple[Decimal, Decimal, str]]:
    """Parse fixed (non-custom) product_attr size labels."""
    sizes: list[tuple[Decimal, Decimal, str]] = []
    seen: set[str] = set()
    for attr in product.product_attr.all():
        if attr.custom_attribute:
            continue
        if not attr.size or not attr.size.title:
            continue
        label = attr.size.title.strip()
        try:
            w, l = parse_size_label(label)
        except SizeParseError as exc:
            logger.warning("Skip size %r for product %s: %s", label, product.pk, exc)
            continue
        key = normalize_size_key(w, l)
        if key in seen:
            continue
        seen.add(key)
        sizes.append((w, l, label))
    return sizes


def pregenerate_product_glbs(product) -> dict:
    built = []
    errors = []
    for width, length, label in collect_fixed_sizes(product):
        try:
            path = get_or_build_glb(product, width, length)
            built.append({"label": label, "key": normalize_size_key(width, length), "path": str(path)})
        except Exception as exc:
            logger.exception("GLB pregenerate failed %s %s", product.pk, label)
            errors.append({"label": label, "error": str(exc)})
    return {"built": built, "errors": errors}


def media_url_for_glb(path: Path) -> str:
    rel = path.relative_to(Path(settings.MEDIA_ROOT)).as_posix()
    base = settings.MEDIA_URL.rstrip("/")
    return f"{base}/{rel}"
