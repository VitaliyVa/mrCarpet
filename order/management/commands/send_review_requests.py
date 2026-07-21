"""
Send the review invitations that have come due.

A command rather than only a scheduler hook, so it can be run by hand after
a backlog, and dry-run before it mails anyone.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from order.review_request import DELAY_DAYS, build_email, due_orders, send_due


class Command(BaseCommand):
    help = "Надіслати прохання про відгук для виконаних замовлень"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Показати, кому пішов би лист, і нічого не надсилати.",
        )
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args, **options):
        pending = list(due_orders()[: options["limit"]])
        self.stdout.write(
            f"Виконаних замовлень старших за {DELAY_DAYS} дн. без листа: {len(pending)}"
        )

        if options["dry_run"]:
            for order in pending:
                built = build_email(order)
                self.stdout.write(
                    f"  #{order.order_number} → {order.email} "
                    f"({'готовий' if built else 'без товарів, пропуск'})"
                )
            return

        sent = send_due(limit=options["limit"])
        self.stdout.write(f"Надіслано: {sent}")
