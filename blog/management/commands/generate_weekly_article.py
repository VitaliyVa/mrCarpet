"""
Draft the next article from the topic queue.

Runnable by hand — which is how the first few get written, and how a missed
week gets caught up.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from blog.models import ArticleTopic
from blog.services.weekly_topic import generate_next


class Command(BaseCommand):
    help = "Згенерувати чернетку статті з наступної теми в черзі"

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=1,
            help="Скільки чернеток згенерувати підряд.",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Не слати повідомлення в Telegram.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Показати наступні теми і нічого не генерувати.",
        )

    def handle(self, *args, **options):
        if options["dry_run"]:
            upcoming = ArticleTopic.objects.filter(
                status=ArticleTopic.Status.PENDING
            )[: options["count"]]
            for topic in upcoming:
                self.stdout.write(f"{topic.rank:3}. {topic.title} → {topic.target_path}")
            return

        for _ in range(max(1, options["count"])):
            result = generate_next(notify=not options["quiet"])
            if not result.get("ok"):
                self.stderr.write(f"Помилка: {result.get('error')}")
                return
            self.stdout.write(
                f"Чернетка готова: {result['topic']} (article #{result['article_id']})"
            )
