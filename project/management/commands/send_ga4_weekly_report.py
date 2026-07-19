"""Send GA4 analytics dashboard to Telegram once."""

from django.core.management.base import BaseCommand

from project.ga4_telegram_report import send_ga4_dashboard_report, send_weekly_ga4_report


class Command(BaseCommand):
    help = "Send GA4 dashboard (charts) to Telegram"

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=7)
        parser.add_argument(
            "--weekly",
            action="store_true",
            help="Use weekly intro + TelegramSettings chat",
        )

    def handle(self, *args, **options):
        if options["weekly"]:
            result = send_weekly_ga4_report()
        else:
            result = send_ga4_dashboard_report(days=options["days"])
        if result.get("ok"):
            self.stdout.write(
                self.style.SUCCESS(
                    f"OK photos={result.get('photos_count')} days={result.get('days')}"
                )
            )
        else:
            self.stderr.write(self.style.ERROR(result.get("error") or "failed"))
            raise SystemExit(1)
