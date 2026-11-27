"""Plain Instagram captions with one topic emoji for 90 scheduled carousels.

The owner prefers the short factual text (what the article covers) over the
story-like lines; emotion comes from emojis. Old and new templates live in
social/data/ig_caption_plain_2026_11.json.

Safety for prod: waiting posts only (never queued/published), only when the
stored caption is exactly the one rendered from the old template (hand edits
stay), idempotent, never raises, reverse is a no-op. No model methods are
used (historical models do not have them).
"""

import json
from pathlib import Path

from django.db import migrations

DATA = Path(__file__).resolve().parent.parent / "data" / "ig_caption_plain_2026_11.json"
WAITING = ("draft", "scheduled", "failed")
IG_PROFILE_LINE = "Повна стаття за посиланням у профілі"


def render(template: str) -> str:
    """Same result as social.services.article_post.render_caption for instagram."""
    text = (template or "").strip()
    if IG_PROFILE_LINE.lower() not in text.lower():
        text = f"{text}\n\n{IG_PROFILE_LINE}".strip()
    return text


def forwards(apps, schema_editor):
    try:
        rewrites = json.loads(DATA.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        print(f"  [social] ig captions skipped: {exc}")
        return

    SocialPost = apps.get_model("social", "SocialPost")
    changed = 0
    for slug, texts in rewrites.items():
        try:
            old, new = render(texts["old"]), render(texts["new"])
            for post in SocialPost.objects.filter(
                article__slug=slug, status__in=WAITING, caption_ig=old
            ):
                post.caption_ig = new
                post.save(update_fields=["caption_ig"])
                changed += 1
        except Exception as exc:  # pragma: no cover - defensive
            print(f"  [social] {slug}: ig caption not updated: {exc}")
    print(f"\n  [social] instagram captions made plain: {changed}")


class Migration(migrations.Migration):
    dependencies = [
        ("social", "0029_restore_original_facebook_captions"),
    ]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
