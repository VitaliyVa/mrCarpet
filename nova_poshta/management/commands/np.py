from django.core.management.base import BaseCommand

from ...models import (
    Area,
    SettlementType,
    Warehouse,
    Settlement,
    WarehouseType,
)
from ...utils import get_full_response, get_response


def test_api():
    response = get_response("Address", "getSettlementTypes")
    if response["errors"]:
        raise Exception(response["errors"])


def create_settlement_types():
    response = get_response("Address", "getSettlementTypes")
    bulk_create_list = []
    bulk_update_list = []
    for obj in response["data"]:
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
    SettlementType.objects.bulk_update(
        bulk_update_list, fields=["title", "short_desc", "ref"]
    )
    print("SettlementType bulk_create", len(bulk_create_list))
    print("SettlementType bulk_update", len(bulk_update_list))


def create_warehouse_types():
    response = get_response("Address", "getWarehouseTypes")
    bulk_create_list = []
    bulk_update_list = []
    for obj in response["data"]:
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
    WarehouseType.objects.bulk_update(bulk_update_list, fields=["title", "ref"])
    print("WarehouseType bulk_create", len(bulk_create_list))
    print("WarehouseType bulk_update", len(bulk_update_list))


def create_areas():
    response = get_response("Address", "getAreas")
    bulk_create_list = []
    bulk_update_list = []
    for obj in response["data"]:
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
    Area.objects.bulk_update(bulk_update_list, fields=["title", "ref"])
    print("Area bulk_create", len(bulk_create_list))
    print("Area bulk_update", len(bulk_update_list))


def create_cities():
    response = get_full_response("Address", "getCities")
    bulk_create_list = []
    bulk_update_list = []
    for obj in response["data"]:
        title = obj.get("Description")
        ref = obj.get("Ref")
        type = SettlementType.objects.get(ref=obj.get("SettlementType"))
        area = Area.objects.get(ref=obj.get("Area"))
        settlement = Settlement.objects.filter(ref=ref).first()
        if settlement:
            settlement.title = title
            settlement.ref = ref
            bulk_update_list.append(settlement)
        else:
            bulk_create_list.append(
                Settlement(title=title, type=type, ref=ref, area=area)
            )
    Settlement.objects.bulk_create(bulk_create_list)
    Settlement.objects.bulk_update(bulk_update_list, fields=["title", "ref"])
    print("Settlement bulk_create", len(bulk_create_list))
    print("Settlement bulk_update", len(bulk_update_list))


def create_warehouses():
    settlements = Settlement.objects.all()
    bulk_create_list = []
    bulk_update_list = []
    for settlement in settlements:
        properties = {"CityRef": settlement.ref}
        response = get_response("Address", "getWarehouses", properties)
        if response["data"]:
            for obj in response["data"]:
                title = obj.get("Description")
                ref = obj.get("Ref")
                short_address = obj["ShortAddress"]
                type = WarehouseType.objects.get(ref=obj["TypeOfWarehouse"])
                warehouse = Warehouse.objects.filter(ref=ref).first()
                if warehouse:
                    warehouse.title = title
                    warehouse.ref = ref
                    bulk_update_list.append(warehouse)
                else:
                    bulk_create_list.append(
                        Warehouse(
                            title=title,
                            short_address=short_address,
                            type=type,
                            settlement=settlement,
                            ref=ref,
                        )
                    )
    Warehouse.objects.bulk_create(bulk_create_list)
    Warehouse.objects.bulk_update(bulk_update_list, fields=["title", "ref"])
    print("Warehouse bulk_create", len(bulk_create_list))
    print("Warehouse bulk_update", len(bulk_update_list))


class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        test_api()
        create_settlement_types()
        create_warehouse_types()
        create_areas()
        create_cities()
        create_warehouses()