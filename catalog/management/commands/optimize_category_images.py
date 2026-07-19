"""Re-encode ProductCategory images to small WebP for homepage tiles."""

from __future__ import annotations

from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from catalog.image_optimize import optimize_category_image
from catalog.models import ProductCategory


class Command(BaseCommand):
    help = "Optimize category images to ~280px WebP (homepage catalog tiles)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--min-bytes",
            type=int,
            default=40_000,
            help="Skip files smaller than this (already optimized).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report only, do not write.",
        )

    def handle(self, *args, **options):
        min_bytes: int = options["min_bytes"]
        dry_run: bool = options["dry_run"]
        converted = 0
        skipped = 0
        errors = 0

        qs = ProductCategory.objects.exclude(image="").exclude(image=None)
        for cat in qs.iterator():
            try:
                if not cat.image:
                    skipped += 1
                    continue
                cat.image.open("rb")
                data = cat.image.read()
                cat.image.close()
                if not data or len(data) < min_bytes:
                    skipped += 1
                    continue
                if dry_run:
                    self.stdout.write(
                        f"[dry-run] {cat.pk} {cat.title}: {len(data)} bytes → optimize"
                    )
                    converted += 1
                    continue

                optimized = optimize_category_image(data)
                stem = Path(cat.image.name).stem
                cat.image.save(f"{stem}.webp", ContentFile(optimized), save=True)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✓ {cat.pk} {cat.title}: {len(data)} → {len(optimized)} bytes"
                    )
                )
                converted += 1
            except Exception as exc:
                errors += 1
                self.stderr.write(f"✗ {getattr(cat, 'pk', '?')} {getattr(cat, 'title', '')}: {exc}")

        self.stdout.write(
            f"Done. converted={converted} skipped={skipped} errors={errors}"
        )
