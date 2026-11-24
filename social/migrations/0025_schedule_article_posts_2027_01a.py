"""Schedule Instagram/Facebook carousels for the January 2027 article batch.

Each post goes out at 18:00 Kyiv on the day its article is published (the
content-scheduler daemon releases it, and never before the article is
public). Safety for prod:
- idempotent (schedule_article_post updates the post for the same article
  and time instead of duplicating it);
- one bad item is logged and skipped, never raised: the web container runs
  `migrate` before gunicorn, so an exception here would keep the site down;
- reverse is a no-op.
"""

import json
from datetime import datetime
from pathlib import Path

from django.db import migrations

DATA = Path(__file__).resolve().parent.parent / "data" / "article_post_specs_2027_01a.json"
ARTICLES = (
    Path(__file__).resolve().parent.parent.parent / "blog" / "data" / "articles_2027_01a.json"
)


def forwards(apps, schema_editor):
    try:
        from social.services.article_post import schedule_article_post

        specs = json.loads(DATA.read_text(encoding="utf-8"))
        days = {
            a["slug"]: a["publish_at"][:10]
            for a in json.loads(ARTICLES.read_text(encoding="utf-8"))
        }
    except Exception as exc:  # pragma: no cover - defensive
        print(f"  [social] article posts skipped: {exc}")
        return

    done = 0
    for slug, spec in specs.items():
        day = days.get(slug)
        if not day:
            continue
        try:
            schedule_article_post(slug, spec, f"{day} 18:00")
            done += 1
        except Exception as exc:  # pragma: no cover - defensive
            print(f"  [social] {slug}: not scheduled: {exc}")
    print(f"\n  [social] scheduled {done} of {len(specs)} article posts")


class Migration(migrations.Migration):
    dependencies = [
        ("social", "0024_schedule_article_posts_2026_12b"),
        ("blog", "0010_seed_articles_2027_01a"),
        ("catalog", "0047_fill_product_descriptions_2026_11"),
    ]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
