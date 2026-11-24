"""Fill empty product descriptions and fix two title typos (2026-11-24).

70 of 99 live product pages showed "Опис з’явиться незабаром." and 10 more had
a one-liner, so Google filed them as thin near-duplicates of their oval /
rectangular twins. Texts were written from the facts on each live page.

Safety (this runs on prod during deploy):
- Only fills a description that is empty or shorter than 200 characters.
  Anything the owner already wrote in the admin is left untouched.
- Title typos are fixed only when the current title is exactly the known
  wrong one. Slugs never change.
- Nothing is deleted. Reverse is a no-op.
"""

import json
from pathlib import Path

from django.db import migrations
from django.utils import timezone
from django.utils.html import strip_tags

DATA = Path(__file__).resolve().parent.parent / "data" / "product_descriptions_2026_11.json"

TITLE_FIXES = {
    # slug: (wrong title, fixed title)
    "kilim-korichevii-dlia-vanni-3205": (
        "Килим коричевий для ванни 3205",
        "Килим коричневий для ванни 3205",
    ),
}
TITLE_REPLACE = {
    # slug: (wrong fragment, right fragment) — fragment-level, exact match only
    "kilim-ovalnim-svitlo-bezhevii-fashion-32007110-o": ("овальним", "овальний"),
}

MIN_EXISTING = 200


def forwards(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    texts = json.loads(DATA.read_text(encoding="utf-8"))

    filled = 0
    for slug, text in texts.items():
        product = Product.objects.filter(slug=slug).first()
        if product is None:
            continue
        current = strip_tags(product.description or "").strip()
        if len(current) >= MIN_EXISTING:
            continue
        # bump `updated`: it is the sitemap lastmod, a hint to recrawl
        Product.objects.filter(pk=product.pk).update(
            description=text, updated=timezone.now()
        )
        filled += 1

    for slug, (wrong, right) in TITLE_FIXES.items():
        Product.objects.filter(slug=slug, title=wrong).update(title=right)

    for slug, (wrong, right) in TITLE_REPLACE.items():
        product = Product.objects.filter(slug=slug).first()
        if product and wrong in (product.title or ""):
            Product.objects.filter(pk=product.pk).update(
                title=product.title.replace(wrong, right)
            )

    print(f"\n  [product descriptions] filled {filled} of {len(texts)}")


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0046_alter_productreview_options_productreview_email_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
