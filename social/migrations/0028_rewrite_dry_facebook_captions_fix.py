"""Second pass of 0027: livelier Facebook captions for 90 scheduled carousels.

0027 built the article link with Article.get_absolute_url(), which historical
migration models do not have, so it skipped every post. Here the link is taken
from the stored caption itself (the post already carries the right one), and
no model methods are used.

Safety for prod (same as 0027):
- only posts still waiting (draft/scheduled/failed), never queued/published;
- only when the stored caption is exactly the one rendered from the old
  template, so a caption edited by hand in the admin is left alone;
- idempotent, one bad item is logged and skipped, reverse is a no-op.
"""

import json
import re
from pathlib import Path

from django.db import migrations

DATA = Path(__file__).resolve().parent.parent / "data" / "fb_caption_rewrite_2026_11.json"
WAITING = ("draft", "scheduled", "failed")
LINK_RE = re.compile(r"https?://\S+")


def render(template: str, link: str) -> str:
    """Same result as social.services.article_post.render_caption for facebook."""
    text = (template or "").strip()
    if "{link}" in text:
        return text.replace("{link}", link)
    if link not in text:
        return f"{text}\n\n{link}".strip()
    return text


def forwards(apps, schema_editor):
    try:
        rewrites = json.loads(DATA.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        print(f"  [social] fb captions skipped: {exc}")
        return

    SocialPost = apps.get_model("social", "SocialPost")
    changed = 0
    for slug, texts in rewrites.items():
        try:
            for post in SocialPost.objects.filter(article__slug=slug, status__in=WAITING):
                match = LINK_RE.search(post.caption_fb or "")
                if not match:
                    continue
                link = match.group(0)
                old = render(texts["old"], link)
                new = render(texts["new"], link)
                if post.caption_fb == new or post.caption_fb != old:
                    continue  # done already, or edited by hand
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
        ("social", "0027_rewrite_dry_facebook_captions"),
    ]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
