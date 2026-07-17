"""Sync Nova Poshta reference data into local DB (settlements, warehouses, …)."""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand

from ...models import (
    Area,
    SettlementType,
    Warehouse,
    Settlement,
    WarehouseType,
)
from ...utils import get_full_response, get_response

logger = logging.getLogger("nova_poshta.sync")


def test_api():
    response = get_response("Address", "getSettlementTypes")
    errors = response.get("errors") or []
    if errors:
        raise RuntimeError(f"Nova Poshta API error: {errors}")
    if not response.get("success", True) and not response.get("data"):
        raise RuntimeError(f"Nova Poshta API unsuccessful: {response}")


def create_settlement_types():
    response = get_response("Address", "getSettlementTypes")
    bulk_create_list = []
    bulk_update_list = []
    for obj in response.get("data") or []:
        title = obj.get("Description")
        short_desc = obj.get("Code")
        ref = obj.get("Ref")
        settlement_type = SettlementType.objects.filter(ref=ref).first()
        if settlement_type:
            settlement_type.title = title
            settlement_type.short_desc = short_desc
            settlement_type.ref = ref
            bulk_update_list.append(settlement_type)
        else:
            bulk_create_list.append(
                SettlementType(title=title, short_desc=short_desc, ref=ref)
            )
    SettlementType.objects.bulk_create(bulk_create_list)
    if bulk_update_list:
        SettlementType.objects.bulk_update(
            bulk_update_list, fields=["title", "short_desc", "ref"]
        )
    logger.info(
        "SettlementType create=%s update=%s",
        len(bulk_create_list),
        len(bulk_update_list),
    )


def create_warehouse_types():
    response = get_response("Address", "getWarehouseTypes")
    bulk_create_list = []
    bulk_update_list = []
    for obj in response.get("data") or []:
        title = obj.get("Description")
        ref = obj.get("Ref")
        warehouse_type = WarehouseType.objects.filter(ref=ref).first()
        if warehouse_type:
            warehouse_type.title = title
            warehouse_type.ref = ref
            bulk_update_list.append(warehouse_type)
        else:
            bulk_create_list.append(WarehouseType(title=title, ref=ref))
    WarehouseType.objects.bulk_create(bulk_create_list)
    if bulk_update_list:
        WarehouseType.objects.bulk_update(bulk_update_list, fields=["title", "ref"])
    logger.info(
        "WarehouseType create=%s update=%s",
        len(bulk_create_list),
        len(bulk_update_list),
    )


def create_areas():
    response = get_response("Address", "getAreas")
    bulk_create_list = []
    bulk_update_list = []
    for obj in response.get("data") or []:
        title = obj.get("Description")
        ref = obj.get("Ref")
        area = Area.objects.filter(ref=ref).first()
        if area:
            area.title = title
            area.ref = ref
            bulk_update_list.append(area)
        else:
            bulk_create_list.append(Area(title=title, ref=ref))
    Area.objects.bulk_create(bulk_create_list)
    if bulk_update_list:
        Area.objects.bulk_update(bulk_update_list, fields=["title", "ref"])
    logger.info("Area create=%s update=%s", len(bulk_create_list), len(bulk_update_list))


def create_cities():
    """Full paginated getCities — single-page get_response is not enough for prod."""
    response = get_full_response("Address", "getCities")
    data = response.get("data") or []
    logger.info("getCities downloaded=%s", len(data))

    type_by_ref = {t.ref: t for t in SettlementType.objects.all()}
    area_by_ref = {a.ref: a for a in Area.objects.all()}
    existing = {s.ref: s for s in Settlement.objects.exclude(ref__isnull=True)}

    bulk_create_list = []
    bulk_update_list = []
    skipped = 0

    for obj in data:
        title = obj.get("Description")
        ref = obj.get("Ref")
        type_ref = obj.get("SettlementType")
        area_ref = obj.get("Area")
        stype = type_by_ref.get(type_ref)
        area = area_by_ref.get(area_ref)
        if not stype or not area or not ref:
            skipped += 1
            continue

        settlement = existing.get(ref)
        if settlement:
            settlement.title = title
            settlement.type = stype
            settlement.area = area
            bulk_update_list.append(settlement)
        else:
            bulk_create_list.append(
                Settlement(title=title, type=stype, ref=ref, area=area)
            )

    # chunk bulk ops
    chunk = 1000
    for i in range(0, len(bulk_create_list), chunk):
        Settlement.objects.bulk_create(bulk_create_list[i : i + chunk])
    for i in range(0, len(bulk_update_list), chunk):
        Settlement.objects.bulk_update(
            bulk_update_list[i : i + chunk], fields=["title", "type", "area"]
        )

    logger.info(
        "Settlement create=%s update=%s skipped=%s total_now=%s",
        len(bulk_create_list),
        len(bulk_update_list),
        skipped,
        Settlement.objects.count(),
    )


def create_warehouses():
    response = get_full_response("Address", "getWarehouses")
    data = response.get("data") or []
    logger.info("getWarehouses downloaded=%s", len(data))

    type_by_ref = {t.ref: t for t in WarehouseType.objects.all()}
    settlement_by_ref = {
        s.ref: s for s in Settlement.objects.exclude(ref__isnull=True).only("id", "ref")
    }
    existing = {w.ref: w for w in Warehouse.objects.exclude(ref__isnull=True)}

    bulk_create_list = []
    bulk_update_list = []
    skipped = 0

    for obj in data:
        title = obj.get("Description")
        ref = obj.get("Ref")
        short_address = obj.get("ShortAddress") or ""
        wtype = type_by_ref.get(obj.get("TypeOfWarehouse"))
        settlement = settlement_by_ref.get(obj.get("CityRef"))
        if not wtype or not settlement or not ref:
            skipped += 1
            continue

        warehouse = existing.get(ref)
        if warehouse:
            warehouse.title = title
            warehouse.short_address = short_address
            warehouse.type = wtype
            warehouse.settlement = settlement
            warehouse.ref = ref
            bulk_update_list.append(warehouse)
        else:
            bulk_create_list.append(
                Warehouse(
                    title=title,
                    short_address=short_address,
                    type=wtype,
                    settlement=settlement,
                    ref=ref,
                )
            )

    chunk = 1000
    for i in range(0, len(bulk_create_list), chunk):
        Warehouse.objects.bulk_create(bulk_create_list[i : i + chunk])
    for i in range(0, len(bulk_update_list), chunk):
        Warehouse.objects.bulk_update(
            bulk_update_list[i : i + chunk],
            fields=["title", "short_address", "type", "settlement", "ref"],
        )

    logger.info(
        "Warehouse create=%s update=%s skipped=%s total_now=%s",
        len(bulk_create_list),
        len(bulk_update_list),
        skipped,
        Warehouse.objects.count(),
    )


class Command(BaseCommand):
    help = (
        "Sync Nova Poshta dictionaries into DB. "
        "Prod empty settlements → run this once (needs NOVA_POSHTA_API_KEY)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--only",
            type=str,
            default="",
            help="Comma list: types,areas,cities,warehouses (default: all)",
        )
        parser.add_argument(
            "--skip-warehouses",
            action="store_true",
            help="Sync types/areas/cities only (faster; enough for city search)",
        )

    def handle(self, *args, **options):
        only_raw = (options.get("only") or "").strip()
        only = {p.strip() for p in only_raw.split(",") if p.strip()} if only_raw else set()
        skip_wh = options.get("skip_warehouses")

        def want(name: str) -> bool:
            if only:
                return name in only
            if skip_wh and name == "warehouses":
                return False
            return True

        self.stdout.write("NP sync: testing API key…")
        test_api()
        self.stdout.write(self.style.SUCCESS("API OK"))

        if want("types"):
            self.stdout.write("→ settlement/warehouse types")
            create_settlement_types()
            create_warehouse_types()
        if want("areas"):
            self.stdout.write("→ areas")
            create_areas()
        if want("cities"):
            self.stdout.write("→ cities (paginated, may take several minutes)")
            create_cities()
        if want("warehouses"):
            self.stdout.write("→ warehouses (paginated, long)")
            create_warehouses()

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. settlements={Settlement.objects.count()} "
                f"warehouses={Warehouse.objects.count()}"
            )
        )
