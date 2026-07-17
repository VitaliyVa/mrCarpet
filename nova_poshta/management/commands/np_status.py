"""Print Nova Poshta local cache counts (diagnose empty prod settlements)."""

from django.core.management.base import BaseCommand

from nova_poshta.models import (
    Area,
    Settlement,
    SettlementType,
    Warehouse,
    WarehouseType,
)
from nova_poshta.utils import get_api_key


class Command(BaseCommand):
    help = "Show NP dictionary counts + whether API key is configured"

    def handle(self, *args, **options):
        key_ok = False
        key_err = ""
        try:
            key = get_api_key()
            key_ok = bool(key)
        except Exception as exc:
            key_err = str(exc)

        self.stdout.write("=== Nova Poshta local cache ===")
        self.stdout.write(f"SettlementType: {SettlementType.objects.count()}")
        self.stdout.write(f"WarehouseType:  {WarehouseType.objects.count()}")
        self.stdout.write(f"Area:           {Area.objects.count()}")
        self.stdout.write(f"Settlement:     {Settlement.objects.count()}")
        self.stdout.write(f"Warehouse:      {Warehouse.objects.count()}")
        kyiv = Settlement.objects.filter(title="Київ").count()
        self.stdout.write(f"Settlement title exact «Київ»: {kyiv}")
        if key_ok:
            self.stdout.write(self.style.SUCCESS("API key: configured"))
        else:
            self.stdout.write(self.style.ERROR(f"API key: MISSING ({key_err})"))

        if Settlement.objects.count() == 0:
            self.stdout.write(
                self.style.WARNING(
                    "Settlements empty → run: python manage.py np --skip-warehouses"
                )
            )
