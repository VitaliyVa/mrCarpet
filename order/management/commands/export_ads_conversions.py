"""Write paid orders with an ad click id as a Google Ads offline conversion CSV.

    python manage.py export_ads_conversions                  # last 30 days, stdout
    python manage.py export_ads_conversions --days 7 -o /srv/exports/ads.csv
    python manage.py export_ads_conversions --name "Оплачене замовлення" --with-braid

The conversion name must match the offline conversion action in Google Ads
exactly. Rows carry the order number as Order ID, so uploading the same
order twice does not count it twice.
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from order.ads_conversions import DEFAULT_CONVERSION_NAME, conversion_rows, write_csv


class Command(BaseCommand):
    help = "Google Ads offline click conversions (CSV) for paid orders with gclid."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Only conversions from the last N days (default 30).",
        )
        parser.add_argument(
            "--name",
            default=DEFAULT_CONVERSION_NAME,
            help="Conversion action name as set up in Google Ads.",
        )
        parser.add_argument(
            "-o",
            "--output",
            default="",
            help="File path to write (default: stdout).",
        )
        parser.add_argument(
            "--with-braid",
            action="store_true",
            help="Add GBRAID / WBRAID columns and orders that have only those.",
        )

    def handle(self, *args, **opts):
        days = max(int(opts["days"]), 1)
        since = timezone.now() - timedelta(days=days)
        rows = conversion_rows(
            conversion_name=opts["name"],
            since=since,
            with_braid=opts["with_braid"],
        )
        path = opts["output"]
        if path:
            with open(path, "w", encoding="utf-8", newline="") as fp:
                write_csv(fp, rows, with_braid=opts["with_braid"])
            self.stderr.write(f"{len(rows)} conversions written to {path}")
        else:
            write_csv(self.stdout, rows, with_braid=opts["with_braid"])
            self.stderr.write(f"{len(rows)} conversions")
