"""
Create a scheduled IG + FB carousel announcing a blog article, from a spec.

    python manage.py create_article_social_post <slug> --spec spec.json --at "2026-12-01 18:00"
    python manage.py create_article_social_post <slug> --spec spec.json --dry-run [--out folder]

--at is Kyiv time. --dry-run renders the slides to a folder only (default:
media/social/article_cards/<slug>/preview/) and touches no database rows.
The tiktok_scheduler tick publishes the post once --at has passed and the
article itself is public.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from social.services.article_post import KYIV


class Command(BaseCommand):
    help = "Render article carousel slides and schedule a SocialPost (IG + FB)"

    def add_arguments(self, parser):
        parser.add_argument("slug", help="Article slug")
        parser.add_argument("--spec", required=True, help="Path to spec JSON")
        parser.add_argument("--at", help='Kyiv time, e.g. "2026-12-01 18:00"')
        parser.add_argument("--dry-run", action="store_true", help="Only render slides")
        parser.add_argument("--out", help="Folder for --dry-run slides")

    def handle(self, *args, **options):
        from blog.models import Article
        from blog.services.social_cards import save_slides_to_dir, storage_dir
        from social.services.article_post import (
            SpecError,
            normalize_spec,
            parse_at,
            render_spec_slides,
            schedule_article_post,
        )

        try:
            spec = json.loads(Path(options["spec"]).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise CommandError(f"spec: {exc}")

        slug = options["slug"]
        try:
            if options["dry_run"]:
                article = Article.objects.filter(slug=slug).first()
                if article is None:
                    raise SpecError(f"Статті зі slug «{slug}» немає")
                slides = render_spec_slides(article, normalize_spec(spec))
                out = options.get("out") or (
                    Path(settings.MEDIA_ROOT) / storage_dir(article, "preview")
                )
                for path in save_slides_to_dir(slides, out):
                    self.stdout.write(path)
                self.stdout.write(self.style.SUCCESS(f"dry run: {len(slides)} slide(s)"))
                return

            if not options.get("at"):
                raise CommandError("--at is required (or use --dry-run)")
            post = schedule_article_post(slug, spec, parse_at(options["at"]))
        except SpecError as exc:
            raise CommandError(str(exc))

        article = post.article
        note = "" if article.is_public_at(post.scheduled_at) else (
            " (стаття ще не публічна на цей час: пост чекатиме на неї)"
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"SocialPost #{post.pk} [{post.status}] at {timezone.localtime(post.scheduled_at, KYIV):%Y-%m-%d %H:%M} (Київ), "
                f"{post.images.count()} slide(s){note}"
            )
        )
