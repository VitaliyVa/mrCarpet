"""Прибирання покинутих кошиків.

Історично context processor створював Cart на кожен перегляд сторінки, тож
БД обростала порожніми анонімними кошиками (~150/добу від ботів).

НІКОЛИ не чіпаємо кошики, повʼязані з замовленням: склад замовлення
зберігається саме в cart_products, і видалення кошика знищило б історію
покупки. Тому фільтр жорсткий: анонімний + без order + ordered=False.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone

from cart.models import Cart

DEFAULT_EMPTY_DAYS = 7
DEFAULT_ABANDONED_DAYS = 90


def _safe_base_qs():
    """Кошики, які взагалі можна розглядати до видалення."""
    return Cart.objects.filter(
        user__isnull=True,      # у залогінених кошик — частина акаунта
        order__isnull=True,     # звʼязок із замовленням = історія покупки
        ordered=False,          # оформлений кошик не чіпаємо навіть без FK
    )


def cleanup_carts(
    empty_days: int = DEFAULT_EMPTY_DAYS,
    abandoned_days: int | None = DEFAULT_ABANDONED_DAYS,
    dry_run: bool = False,
) -> dict:
    now = timezone.now()
    base = _safe_base_qs().annotate(n_products=Count("cart_products"))

    empty_qs = base.filter(
        n_products=0, updated__lt=now - timedelta(days=empty_days)
    )
    empty_count = empty_qs.count()

    abandoned_count = 0
    abandoned_qs = None
    if abandoned_days:
        abandoned_qs = base.filter(
            n_products__gt=0, updated__lt=now - timedelta(days=abandoned_days)
        )
        abandoned_count = abandoned_qs.count()

    if not dry_run:
        # values_list + filter(pk__in) — annotate() не дружить з delete()
        if empty_count:
            Cart.objects.filter(
                pk__in=list(empty_qs.values_list("pk", flat=True))
            ).delete()
        if abandoned_count:
            Cart.objects.filter(
                pk__in=list(abandoned_qs.values_list("pk", flat=True))
            ).delete()

    return {
        "empty_deleted": empty_count,
        "abandoned_deleted": abandoned_count,
        "remaining": Cart.objects.count(),
        "dry_run": dry_run,
    }


class Command(BaseCommand):
    help = "Delete abandoned anonymous carts (never touches ordered ones)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--empty-days",
            type=int,
            default=DEFAULT_EMPTY_DAYS,
            help=f"Порожні анонімні кошики, старші за N днів (типово {DEFAULT_EMPTY_DAYS})",
        )
        parser.add_argument(
            "--abandoned-days",
            type=int,
            default=DEFAULT_ABANDONED_DAYS,
            help=(
                "Анонімні кошики З товарами, старші за N днів "
                f"(типово {DEFAULT_ABANDONED_DAYS}; 0 = не чіпати)"
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Тільки показати, скільки б видалилось",
        )

    def handle(self, *args, **options):
        total_before = Cart.objects.count()
        result = cleanup_carts(
            empty_days=options["empty_days"],
            abandoned_days=options["abandoned_days"] or None,
            dry_run=options["dry_run"],
        )
        prefix = "[dry-run] " if result["dry_run"] else ""
        self.stdout.write(f"{prefix}було кошиків: {total_before}")
        self.stdout.write(f"{prefix}порожніх видалено: {result['empty_deleted']}")
        self.stdout.write(
            f"{prefix}покинутих з товарами видалено: {result['abandoned_deleted']}"
        )
        self.stdout.write(
            self.style.SUCCESS(f"{prefix}лишилось: {result['remaining']}")
        )
