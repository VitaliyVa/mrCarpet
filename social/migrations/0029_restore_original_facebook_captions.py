"""Undo 0028: the owner prefers the original, plain Facebook captions.

Restores the old text (social/data/fb_caption_rewrite_2026_11.json "old") on
posts that still carry exactly the 0028 text. Same safety as 0028: waiting
posts only, a hand-edited caption is left alone, idempotent, never raises.
"""

import json
import re
from pathlib import Path

from django.db import migrations

DATA = Path(__file__).resolve().parent.parent / "data" / "fb_caption_rewrite_2026_11.json"
WAITING = ("draft", "scheduled", "failed")
LINK_RE = re.compile(r"https?://\S+")


def render(template: str, link: str) -> str:
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
        print(f"  [social] fb captions restore skipped: {exc}")
        return

    SocialPost = apps.get_model("social", "SocialPost")
    restored = 0
    for slug, texts in rewrites.items():
        try:
            for post in SocialPost.objects.filter(article__slug=slug, status__in=WAITING):
                match = LINK_RE.search(post.caption_fb or "")
                if not match:
                    continue
                link = match.group(0)
                old = render(texts["old"], link)
                new = render(texts["new"], link)
                if post.caption_fb != new:
                    continue  # already original, or edited by hand
                post.caption_fb = old
                fields = ["caption_fb"]
                if post.caption == new:
                    post.caption = old
                    fields.append("caption")
                post.save(update_fields=fields)
                restored += 1
        except Exception as exc:  # pragma: no cover - defensive
            print(f"  [social] {slug}: fb caption not restored: {exc}")
    print(f"\n  [social] facebook captions restored: {restored}")


class Migration(migrations.Migration):
    dependencies = [
        ("social", "0028_rewrite_dry_facebook_captions_fix"),
    ]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
