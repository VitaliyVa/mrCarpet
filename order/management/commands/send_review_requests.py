"""
Send the review invitations that have come due.

A command rather than only a scheduler hook, so it can be run by hand after
a backlog, and dry-run before it mails anyone.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from order.review_request import (
    DELAY_DAYS,
    ask_staff_due,
    build_email,
    due_orders,
    due_orders_without_email,
    send_due,
)


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

        no_email = list(due_orders_without_email()[: options["limit"]])
        self.stdout.write(
            f"Без email (піде в чат персоналу з готовим текстом): {len(no_email)}"
        )

        if options["dry_run"]:
            for order in pending:
                built = build_email(order)
                self.stdout.write(
                    f"  #{order.order_number} → {order.email} "
                    f"({'готовий' if built else 'без товарів, пропуск'})"
                )
            for order in no_email:
                self.stdout.write(
                    f"  #{order.order_number} → тел. {order.phone or 'немає'} (чат персоналу)"
                )
            return

        sent = send_due(limit=options["limit"])
        self.stdout.write(f"Надіслано: {sent}")
        asked = ask_staff_due(limit=options["limit"])
        self.stdout.write(f"Передано персоналу: {asked}")
