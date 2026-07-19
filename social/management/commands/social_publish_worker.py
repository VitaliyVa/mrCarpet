"""Sync publish worker — process queued SocialPosts (optional cron)."""

from django.core.management.base import BaseCommand

from social.models import SocialPost
from social.services.publish import publish_post


class Command(BaseCommand):
    help = "Publish SocialPosts in queued status"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=10)

    def handle(self, *args, **options):
        qs = SocialPost.objects.filter(status=SocialPost.Status.QUEUED).order_by(
            "created"
        )[: options["limit"]]
        n = 0
        for post in qs:
            self.stdout.write(f"publishing #{post.pk}…")
            publish_post(post.pk)
            n += 1
        self.stdout.write(self.style.SUCCESS(f"Processed {n}"))
