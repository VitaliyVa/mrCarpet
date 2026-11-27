"""Livelier Facebook captions for 90 scheduled article carousels.

The first versions were one dry "what the article covers" sentence. The new
text reuses the warm, short Instagram lines plus a link to the article
(social/data/fb_caption_rewrite_2026_11.json keeps old and new templates).

Safety for prod:
- only posts still waiting (draft/scheduled/failed), never queued/published;
- only when the stored caption is exactly the one rendered from the old
  template, so a caption edited by hand in the admin is left alone;
- idempotent, one bad item is logged and skipped, reverse is a no-op.
"""

import json
from pathlib import Path

from django.db import migrations

DATA = Path(__file__).resolve().parent.parent / "data" / "fb_caption_rewrite_2026_11.json"
WAITING = ("draft", "scheduled", "failed")


def forwards(apps, schema_editor):
    try:
        from social.services.article_post import render_caption
        from social.services.media_urls import article_campaign, article_share_url

        rewrites = json.loads(DATA.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        print(f"  [social] fb captions skipped: {exc}")
        return

    SocialPost = apps.get_model("social", "SocialPost")
    changed = 0
    for slug, texts in rewrites.items():
        try:
            for post in SocialPost.objects.filter(article__slug=slug, status__in=WAITING):
                campaign = (post.utm_campaign or article_campaign(post.article))[:64]
                link = article_share_url(post.article, "facebook", campaign)
                old = render_caption(texts["old"], link, platform="facebook")
                new = render_caption(texts["new"], link, platform="facebook")
                if post.caption_fb == new:
                    continue
                if post.caption_fb != old:
                    continue  # edited by hand: keep it
                post.caption_fb = new
                fields = ["caption_fb"]
                if post.caption == old:
                    post.caption = new
                    fields.append("caption")
                post.save(update_fields=fields)
                changed += 1
        except Exception as exc:  # pragma: no cover - defensive
            print(f"  [social] {slug}: fb caption not updated: {exc}")
    print(f"\n  [social] facebook captions rewritten: {changed}")


class Migration(migrations.Migration):
    dependencies = [
        ("social", "0026_schedule_article_posts_2027_q1"),
    ]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
