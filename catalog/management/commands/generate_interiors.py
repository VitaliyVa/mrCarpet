"""
Generate the missing interior photo for products that have none.

The daily video pipeline builds its 9:16 frame by *extending* an interior
shot — it never recomposes, so the rug keeps its real physical scale. That
makes an interior photo the hard requirement for a product to enter the
rotation at all: catalogue shots on a white background stretch into white.

These images are not private to the video. They appear in the product page
slider with an AI badge, so a bad one is visible to customers, not just to
the scheduler. Hence --limit and --dry-run, and a default that refuses to
run the whole catalogue in one unattended go.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError

from catalog.models import Product, ProductImage
from catalog.services.replicate_product_images import (
    ReplicateGenerationError,
    ReplicateProductImageService,
)
from catalog.services.replicate_prompt_options import GenerationOptions
from catalog.services.scene_size import SceneSizeError, resolve_scene_size

#: Small on purpose. Every image costs money and lands on the storefront;
#: a wrong prompt should waste three, not thirty-six.
DEFAULT_LIMIT = 3


def products_missing_interior():
    """Products that could join the rotation but have no interior shot yet."""
    return (
        Product.admin_objects.filter(images__isnull=False)
        .exclude(images__is_ai=True)
        .distinct()
        .order_by("pk")
    )


def _source_image(product):
    """The catalogue photo the interior is generated from."""
    return (
        product.images.filter(is_ai=False)
        .exclude(image="")
        .order_by("sort_order", "id")
        .first()
    )


class Command(BaseCommand):
    help = "Generate the missing AI interior photo for products that lack one."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=DEFAULT_LIMIT,
            help=f"How many products to process (default {DEFAULT_LIMIT}).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List what would be generated, spend nothing.",
        )
        parser.add_argument(
            "--product",
            type=int,
            nargs="*",
            default=None,
            help="Specific product ids instead of the automatic queue.",
        )

    def handle(self, *args, **options):
        limit = max(1, int(options["limit"]))
        dry = bool(options["dry_run"])
        ids = options.get("product")

        if ids:
            queue = list(Product.admin_objects.filter(pk__in=ids).order_by("pk"))
        else:
            queue = list(products_missing_interior()[:limit])

        total_missing = products_missing_interior().count()
        self.stdout.write(f"без інтер'єру: {total_missing} товар(ів)")
        if not queue:
            self.stdout.write(self.style.SUCCESS("нічого генерувати"))
            return

        self.stdout.write(f"обробляємо: {len(queue)}")
        if dry:
            for product in queue:
                source = _source_image(product)
                mark = "ok" if source else "НЕМАЄ ВИХІДНОГО ФОТО"
                self.stdout.write(f"  #{product.pk} {product.title[:50]} — {mark}")
            self.stdout.write(self.style.WARNING("dry-run: нічого не згенеровано"))
            return

        done, failed = 0, 0
        for product in queue:
            try:
                url = self._generate_for(product)
            except Exception as exc:
                failed += 1
                self.stderr.write(self.style.ERROR(f"#{product.pk}: {exc}"))
                continue
            done += 1
            self.stdout.write(self.style.SUCCESS(f"#{product.pk} {product.title[:40]}"))
            self.stdout.write(f"   {url}")

        self.stdout.write("")
        self.stdout.write(f"готово: {done}, помилок: {failed}")
        left = products_missing_interior().count()
        self.stdout.write(f"лишилось без інтер'єру: {left}")

    def _generate_for(self, product) -> str:
        source = _source_image(product)
        if source is None:
            raise CommandError("немає жодного звичайного фото як джерела")

        try:
            size_info = resolve_scene_size(product_id=product.pk)
        except SceneSizeError as exc:
            # Scene generation needs the real size — without it the model has
            # no idea whether to draw a doormat or a room-filling rug.
            raise CommandError(f"немає розміру: {exc}") from exc

        options = GenerationOptions()
        options.scene = options.scene.with_size(size_info)

        temp_dir = Path(tempfile.mkdtemp(prefix="interior-"))
        try:
            source_path = temp_dir / (Path(source.image.name).name or "source.jpg")
            source.image.open("rb")
            try:
                source_path.write_bytes(source.image.read())
            finally:
                source.image.close()

            service = ReplicateProductImageService()
            try:
                image_bytes, _meta = service.generate_phase(
                    source_path, "scene", options
                )
            except ReplicateGenerationError as exc:
                raise CommandError(str(exc)) from exc
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        last = (
            product.images.order_by("-sort_order").values_list("sort_order", flat=True)
        ).first()
        image = ProductImage(
            product=product,
            # is_ai is what puts the product into the video rotation and what
            # renders the badge in the slider — both follow from this flag.
            is_ai=True,
            sort_order=(last or 0) + 1,
            alt=f"{product.title} в інтер'єрі",
        )
        image.image.save(
            f"interior-{product.pk}.webp", ContentFile(image_bytes), save=True
        )
        return product.get_absolute_url()
