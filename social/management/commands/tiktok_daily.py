"""
Daily TikTok job: generate at night, publish in the evening.

Generation and publishing are separate steps on purpose. The heavy work — two
model calls and an ffmpeg render — runs at 04:00 when the single-worker droplet
is idle, while the post goes out at prime time, when it is actually seen.
"""

from django.core.management.base import BaseCommand

from social.models import TikTokDailyPick
from social.services.tiktok_budget import budget_status
from social.services.tiktok_publish import build_final_video, publish_pick
from social.services.tiktok_rotation import (
    NoEligibleProducts,
    pick_product_for_today,
    rotation_status,
    todays_pick,
)


class Command(BaseCommand):
    help = "Generate and/or publish the day's TikTok post."

    def add_arguments(self, parser):
        parser.add_argument(
            "--generate",
            action="store_true",
            help="Pick a product and render the video (cron at 04:00).",
        )
        parser.add_argument(
            "--publish",
            action="store_true",
            help="Publish the video prepared earlier (cron at 18:00).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Ignore the enabled toggle and any existing pick for today.",
        )
        parser.add_argument(
            "--pick",
            type=int,
            default=0,
            help="Operate on a specific pick id instead of today's.",
        )

    def handle(self, *args, **options):
        if not options["generate"] and not options["publish"]:
            self.stderr.write(
                self.style.ERROR("choose --generate and/or --publish")
            )
            return

        pick = None
        if options["pick"]:
            pick = TikTokDailyPick.objects.filter(pk=options["pick"]).first()
            if pick is None:
                self.stderr.write(self.style.ERROR(f"pick #{options['pick']} not found"))
                return

        if options["generate"]:
            if pick is None:
                try:
                    pick = pick_product_for_today(force=options["force"])
                except NoEligibleProducts as exc:
                    self.stderr.write(self.style.ERROR(str(exc)))
                    return
            self.stdout.write(f"pick #{pick.pk}: {pick.product}")
            try:
                path = build_final_video(pick, force=options["force"])
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"generation failed: {exc}"))
                return
            self.stdout.write(self.style.SUCCESS(f"video ready: {path}"))

        if options["publish"]:
            if pick is None:
                pick = todays_pick()
            if pick is None:
                self.stderr.write(self.style.ERROR("nothing prepared for today"))
                return
            try:
                result = publish_pick(pick, force=options["force"])
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"publish failed: {exc}"))
                return
            self.stdout.write(self.style.SUCCESS(f"published: {result}"))

        rotation = rotation_status()
        budget = budget_status()
        self.stdout.write("")
        self.stdout.write(
            f"cycle {rotation['cycle']}: {rotation['published_this_cycle']}"
            f"/{rotation['pool_size']} published, {rotation['remaining']} left"
        )
        self.stdout.write(
            f"budget: ${budget['spent_usd']} of ${budget['ceiling_usd']} "
            f"({budget['calls']} calls, {budget['failed_calls']} failed)"
        )
