"""Inspect the TikTok daily rotation; optionally take today's pick."""

from django.core.management.base import BaseCommand

from social.models import TikTokDailyPick
from social.services.tiktok_rotation import (
    NoEligibleProducts,
    pick_product_for_today,
    rotation_status,
)


class Command(BaseCommand):
    help = "Show TikTok rotation state (pool, cycle, today's pick)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--pick",
            action="store_true",
            help="Take today's pick if there is none yet (idempotent).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Pick again even if today already has one.",
        )
        parser.add_argument(
            "--history",
            type=int,
            default=0,
            help="Also list the N most recent picks.",
        )

    def handle(self, *args, **options):
        if options["pick"] or options["force"]:
            try:
                pick = pick_product_for_today(force=options["force"])
            except NoEligibleProducts as exc:
                self.stderr.write(self.style.ERROR(str(exc)))
                return
            self.stdout.write(
                self.style.SUCCESS(
                    f"pick #{pick.pk}: {pick.product.title} (cycle {pick.cycle_number})"
                )
            )

        status = rotation_status()
        self.stdout.write("")
        self.stdout.write(f"cycle             : {status['cycle']}")
        self.stdout.write(f"pool (is_ai)      : {status['pool_size']}")
        self.stdout.write(f"published (cycle) : {status['published_this_cycle']}")
        self.stdout.write(f"remaining         : {status['remaining']}")

        today = status["todays_pick"]
        # ASCII only: this runs on a Windows console during development.
        self.stdout.write(
            f"today's pick      : {today.product or '(deleted)'} [{today.status}]"
            if today
            else "today's pick      : none"
        )
        pending = status["pending_generated"]
        if pending:
            self.stdout.write(
                self.style.WARNING(
                    f"unpublished video : pick #{pending.pk} "
                    f"({pending.product}) — reuse instead of regenerating"
                )
            )

        limit = options["history"]
        if limit:
            self.stdout.write("")
            self.stdout.write(f"last {limit} picks:")
            for pick in TikTokDailyPick.objects.all()[:limit]:
                title = pick.product.title[:40] if pick.product_id else "(deleted)"
                self.stdout.write(
                    f"  {pick.picked_at:%Y-%m-%d %H:%M}  c{pick.cycle_number}  "
                    f"{pick.status:10} {title}"
                )
