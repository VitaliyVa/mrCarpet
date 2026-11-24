"""Clearer product titles (2026-11-24): drop «без назви», capitalise brands, add room words.

Title is the H1, card anchor, image alt and the base of the Shopping title.
Safety: a title changes only if it is still exactly the old live value (admin
edits win); slugs never change; nothing deleted; reverse is a no-op.
"""

import json
from pathlib import Path

from django.db import migrations

DATA = Path(__file__).resolve().parent.parent / "data" / "product_titles_2026_11.json"


def forwards(apps, schema_editor):
    Product = apps.get_model("catalog", "Product")
    try:
        items = json.loads(DATA.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover
        print(f"  [titles] skipped: {exc}")
        return
    done = 0
    for slug, v in items.items():
        try:
            done += Product.objects.filter(slug=slug, title=v["old"]).update(title=v["new"])
        except Exception as exc:  # pragma: no cover
            print(f"  [titles] {slug}: {exc}")
    print(f"\n  [titles] renamed {done} of {len(items)} products")


class Migration(migrations.Migration):
    dependencies = [("catalog", "0049_fill_category_texts_2026_11")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
