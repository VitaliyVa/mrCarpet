"""Re-encode ProductCategory images to sharp-enough WebP for homepage tiles."""

from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from catalog.image_optimize import optimize_category_image
from catalog.models import ProductCategory

# Django FileSystemStorage suffix when name collides: _AbCdEfG
_DJANGO_SUFFIX_RE = re.compile(r"_[A-Za-z0-9]{7}$")


def _base_stem(stem: str) -> str:
    return _DJANGO_SUFFIX_RE.sub("", stem)


def find_source_bytes(cat: ProductCategory) -> tuple[bytes, str] | tuple[None, None]:
    """
    Prefer a larger sibling original (png/jpg/webp) over the current tiny WebP.
    Falls back to the current file.
    """
    if not cat.image:
        return None, None

    media_root = Path(settings.MEDIA_ROOT)
    current_rel = Path(cat.image.name)
    current_path = media_root / current_rel
    stem = current_rel.stem
    base = _base_stem(stem)
    parent = current_path.parent

    candidates: list[Path] = []
    if parent.exists():
        for p in parent.iterdir():
            if not p.is_file():
                continue
            if p.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
                continue
            pbase = _base_stem(p.stem)
            if p.stem == stem or p.stem == base or pbase == base:
                candidates.append(p)

    if not candidates and current_path.exists():
        candidates = [current_path]

    if not candidates:
        cat.image.open("rb")
        data = cat.image.read()
        cat.image.close()
        return (data, cat.image.name) if data else (None, None)

    best = max(candidates, key=lambda p: p.stat().st_size)
    return best.read_bytes(), str(best.relative_to(media_root)).replace("\\", "/")


class Command(BaseCommand):
    help = "Optimize category images to WebP (~560px @ q90 by default)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-width",
            type=int,
            default=560,
            help="Max output width in px (default 560 = 2x tile).",
        )
        parser.add_argument(
            "--quality",
            type=int,
            default=90,
            help="WebP quality 1-100 (default 90).",
        )
        parser.add_argument(
            "--min-bytes",
            type=int,
            default=0,
            help="Skip sources smaller than this (0 = never skip by size).",
        )
        parser.add_argument(
            "--from-originals",
            action="store_true",
            help="Prefer larger sibling png/jpg/webp originals when present.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report only, do not write.",
        )

    def handle(self, *args, **options):
        max_width: int = options["max_width"]
        quality: int = options["quality"]
        min_bytes: int = options["min_bytes"]
        from_originals: bool = options["from_originals"]
        dry_run: bool = options["dry_run"]
        converted = 0
        skipped = 0
        errors = 0

        qs = ProductCategory.objects.exclude(image="").exclude(image=None)
        for cat in qs.iterator():
            try:
                if from_originals:
                    data, source_name = find_source_bytes(cat)
                else:
                    cat.image.open("rb")
                    data = cat.image.read()
                    cat.image.close()
                    source_name = cat.image.name

                if not data:
                    skipped += 1
                    continue
                if min_bytes and len(data) < min_bytes:
                    skipped += 1
                    continue

                if dry_run:
                    self.stdout.write(
                        f"[dry-run] {cat.pk} {cat.title}: source={source_name} "
                        f"({len(data)} bytes) → webp max_w={max_width} q={quality}"
                    )
                    converted += 1
                    continue

                optimized = optimize_category_image(
                    data, max_width=max_width, quality=quality
                )
                stem = _base_stem(Path(cat.image.name).stem)
                # Bypass ProductCategory.save() re-encode: write via update + FileField
                cat.image.save(f"{stem}.webp", ContentFile(optimized), save=False)
                ProductCategory.objects.filter(pk=cat.pk).update(image=cat.image.name)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✓ {cat.pk} {cat.title}: {source_name} {len(data)} → "
                        f"{len(optimized)} bytes ({cat.image.name})"
                    )
                )
                converted += 1
            except Exception as exc:
                errors += 1
                self.stderr.write(
                    f"✗ {getattr(cat, 'pk', '?')} {getattr(cat, 'title', '')}: {exc}"
                )

        self.stdout.write(
            f"Done. converted={converted} skipped={skipped} errors={errors}"
        )
