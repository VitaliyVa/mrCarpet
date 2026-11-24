"""Seed the January 2027 article batch (15 articles, 03.01 to 17.01) with their photos.

Safety (runs on prod during deploy):
- Creates an article only if its slug does not exist yet. Never edits or
  deletes an existing article, so anything changed in the admin survives.
- published_at comes from the JSON schedule (Europe/Kyiv). With scheduled
  publishing, a future published_at keeps the article hidden until then.
- Photos are copied into media storage only when the file is missing.
- Also swaps one in-body photo in the 19.12 article about oval/round rugs:
  it reused a photo already shown in the 13.12 article. Only the exact old
  <img> tag is replaced, so an admin edit of that spot is left alone.
- Reverse is a no-op.
"""

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from django.core.files.base import File
from django.core.files.storage import default_storage
from django.db import migrations

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
KYIV = ZoneInfo("Europe/Kyiv")


def forwards(apps, schema_editor):
    Article = apps.get_model("blog", "Article")
    items = json.loads((DATA_DIR / "articles_2027_01a.json").read_text(encoding="utf-8"))
    images = DATA_DIR / "article_images"

    # Never let a file problem stop the deploy: web runs `migrate` before
    # gunicorn starts, so an exception here would keep the site down.
    for path in sorted(images.glob("*.webp")):
        name = f"articles/{path.name}"
        try:
            if not default_storage.exists(name):
                with path.open("rb") as fh:
                    default_storage.save(name, File(fh))
        except Exception as exc:  # pragma: no cover - defensive
            print(f"  [blog] image {name} not copied: {exc}")

    created = 0
    for item in items:
        if Article.objects.filter(slug=item["slug"]).exists():
            continue
        when = datetime.strptime(item["publish_at"], "%Y-%m-%d %H:%M").replace(tzinfo=KYIV)
        Article.objects.create(
            slug=item["slug"],
            title=item["title"],
            meta_title=item["meta_title"],
            meta_description=item["meta_description"],
            description=item["body"],
            image=f"articles/{item['cover']}",
            status="published",
            published_at=when,
        )
        created += 1
    print(f"\n  [blog] created {created} of {len(items)} articles")

    try:
        old = (
            '<img src="/media/articles/napivkruglii-kilimok-na-pidlozi.webp" '
            "alt=\"Світлий напівкруглий килимок з хвилястим краєм на дерев'яній підлозі\">"
        )
        new = (
            '<img src="/media/articles/napivkruglii-pletenyi-kilimok.webp" '
            "alt=\"Напівкруглий плетений килимок на дерев'яній підлозі\">"
        )
        art = Article.objects.filter(slug="ovalnii-kruglii-napivkruglii-kilim").first()
        if art and old in (art.description or ""):
            Article.objects.filter(pk=art.pk).update(description=art.description.replace(old, new))
            print("  [blog] oval article photo swapped")
    except Exception as exc:  # pragma: no cover - defensive
        print(f"  [blog] oval article photo not swapped: {exc}")


class Migration(migrations.Migration):
    dependencies = [("blog", "0009_seed_articles_2026_12b")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
