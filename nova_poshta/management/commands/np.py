"""Sync Nova Poshta reference data into local DB (settlements, warehouses, …)."""

from __future__ import annotations

import logging
import time

from django.core.management.base import BaseCommand
from django.utils import timezone

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
    print("SettlementType bulk_create", len(bulk_create_list))
    print("SettlementType bulk_update", len(bulk_update_list))


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
    print("WarehouseType bulk_create", len(bulk_create_list))
    print("WarehouseType bulk_update", len(bulk_update_list))


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
    print("Area bulk_create", len(bulk_create_list))
    print("Area bulk_update", len(bulk_update_list))


def create_cities():
    """All cities via pagination (single-page get_response was incomplete)."""
    response = get_full_response("Address", "getCities")
    data = response.get("data") or []
    print("getCities downloaded", len(data))

    type_by_ref = {t.ref: t for t in SettlementType.objects.all()}
    area_by_ref = {a.ref: a for a in Area.objects.all()}
    existing = {s.ref: s for s in Settlement.objects.exclude(ref__isnull=True)}

    bulk_create_list = []
    bulk_update_list = []
    skipped = 0

    for obj in data:
        title = obj.get("Description")
        ref = obj.get("Ref")
        stype = type_by_ref.get(obj.get("SettlementType"))
        area = area_by_ref.get(obj.get("Area"))
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

    chunk = 1000
    for i in range(0, len(bulk_create_list), chunk):
        Settlement.objects.bulk_create(bulk_create_list[i : i + chunk])
    for i in range(0, len(bulk_update_list), chunk):
        Settlement.objects.bulk_update(
            bulk_update_list[i : i + chunk], fields=["title", "type", "area"]
        )
    print("Settlement bulk_create", len(bulk_create_list))
    print("Settlement bulk_update", len(bulk_update_list))
    print("Settlement skipped", skipped, "total_now", Settlement.objects.count())


def create_warehouses(
    *,
    city_ref: str | None = None,
    delay_sec: float = 0.35,
    resume: bool = False,
):
    """
    Original project design (see commented loop in old np.py):
    fetch warehouses per settlement CityRef — not one giant paginated dump.

    resume=True → skip settlements that already have ≥1 warehouse in DB.
    """
    type_by_ref = {t.ref: t for t in WarehouseType.objects.all()}
    if not type_by_ref:
        create_warehouse_types()
        type_by_ref = {t.ref: t for t in WarehouseType.objects.all()}

    if city_ref:
        settlements = list(
            Settlement.objects.filter(ref=city_ref).only("id", "ref", "title")
        )
    else:
        qs = (
            Settlement.objects.exclude(ref__isnull=True)
            .exclude(ref="")
            .only("id", "ref", "title", "warehouses_synced_at")
            .order_by("id")
        )
        if resume:
            # Stamp set after successful API call (incl. empty villages)
            qs = qs.filter(warehouses_synced_at__isnull=True)
        settlements = list(qs)

    print(
        f"Warehouses sync for {len(settlements)} settlements"
        f"{' (resume: not yet synced)' if resume else ''}…"
    )

    existing = {
        w.ref: w
        for w in Warehouse.objects.exclude(ref__isnull=True).exclude(ref="")
    }
    bulk_create_list = []
    bulk_update_list = []
    pending_stamp_ids = []
    skipped = 0
    cities_done = 0
    cities_empty = 0
    now = timezone.now

    def flush_warehouses(*, label: str = ""):
        nonlocal bulk_create_list, bulk_update_list, pending_stamp_ids, existing
        if bulk_create_list:
            Warehouse.objects.bulk_create(bulk_create_list, ignore_conflicts=True)
            if label:
                print(f"   flushed create={len(bulk_create_list)}{label}")
            bulk_create_list = []
        if bulk_update_list:
            Warehouse.objects.bulk_update(
                bulk_update_list,
                fields=["title", "short_address", "type", "settlement", "ref"],
            )
            bulk_update_list = []
        if pending_stamp_ids:
            Settlement.objects.filter(pk__in=pending_stamp_ids).update(
                warehouses_synced_at=now()
            )
            pending_stamp_ids = []
        existing = {
            w.ref: w
            for w in Warehouse.objects.exclude(ref__isnull=True).exclude(ref="")
        }

    for settlement in settlements:
        response = get_response(
            "Address",
            "getWarehouses",
            {"CityRef": settlement.ref},
        )
        rows = response.get("data") or []
        if not isinstance(rows, list):
            rows = []
        if not rows:
            cities_empty += 1
            # Empty city: nothing to flush — stamp now for --resume
            Settlement.objects.filter(pk=settlement.pk).update(
                warehouses_synced_at=now()
            )
        for obj in rows:
            if not isinstance(obj, dict):
                skipped += 1
                continue
            title = obj.get("Description")
            ref = obj.get("Ref")
            short_address = obj.get("ShortAddress") or ""
            wtype = type_by_ref.get(obj.get("TypeOfWarehouse"))
            if not wtype or not ref:
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
                wh = Warehouse(
                    title=title,
                    short_address=short_address,
                    type=wtype,
                    settlement=settlement,
                    ref=ref,
                )
                bulk_create_list.append(wh)
                existing[ref] = wh  # avoid dupes within same run

        if rows:
            pending_stamp_ids.append(settlement.pk)

        cities_done += 1
        left = len(settlements) - cities_done
        added = len(rows)
        if cities_done % 10 == 0 or added > 0:
            print(
                f"… {cities_done}/{len(settlements)} left={left} "
                f"«{settlement.title}» +{added} wh "
                f"(empty={cities_empty}, db={Warehouse.objects.count()})"
            )
        if cities_done % 50 == 0:
            flush_warehouses(label="")

        time.sleep(delay_sec)

    flush_warehouses(label=" (last chunk)")

    print(
        f"Warehouses done: cities={cities_done} empty_cities={cities_empty} "
        f"skipped={skipped} total_now={Warehouse.objects.count()}"
    )


class Command(BaseCommand):
    help = "Sync Nova Poshta dictionaries (cities + warehouses per city)."

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
            help="Skip warehouses sync",
        )
        parser.add_argument(
            "--city-ref",
            type=str,
            default="",
            help="Optional: sync warehouses for one CityRef only",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=0.35,
            help="Sleep seconds between per-city warehouse requests (default 0.35)",
        )
        parser.add_argument(
            "--resume",
            action="store_true",
            help="Skip settlements that already have warehouses in DB",
        )

    def handle(self, *args, **options):
        only_raw = (options.get("only") or "").strip()
        only = {p.strip() for p in only_raw.split(",") if p.strip()} if only_raw else set()
        skip_wh = options.get("skip_warehouses")
        city_ref = (options.get("city_ref") or "").strip() or None
        delay = float(options.get("delay") or 0.35)
        resume = bool(options.get("resume"))

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
            create_settlement_types()
            create_warehouse_types()
        if want("areas"):
            create_areas()
        if want("cities"):
            self.stdout.write("→ cities (paginated)")
            create_cities()
        if want("warehouses"):
            self.stdout.write(
                "→ warehouses per city (original design; all settlements)"
                + (f" filter={city_ref}" if city_ref else "")
                + (" resume" if resume else "")
            )
            create_warehouses(city_ref=city_ref, delay_sec=delay, resume=resume)

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. settlements={Settlement.objects.count()} "
                f"warehouses={Warehouse.objects.count()}"
            )
        )
