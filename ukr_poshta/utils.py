import xmltodict
import json
import requests

from ukr_poshta.models import City, UkrOffice

# Example response string
url = "https://www.ukrposhta.ua/address-classifier-ws/get_city_by_region_id_and_district_id_and_city_ua"
headers = {
    "Authorization": "Bearer 62f57bb7-db3d-3d62-ba7c-37ce30bf8bd6"
}


def import_cities():
    r = requests.get(url, headers=headers)
    xml_data = r.text

    data_dict = xmltodict.parse(xml_data)
    entries = data_dict["Entries"]["Entry"]
    # print(data_dict["Entries"]["Entry"]["LOCK_EN"])
    result = []
    for obj in entries:
        data = {
            "region_id": obj["REGION_ID"],
            "district_id": obj["DISTRICT_ID"],
            "longitude": obj["LONGITUDE"],
            "city_type": obj["CITYTYPE_UA"],
            "status": obj["NAME_UA"],
            "region": obj["REGION_UA"],
            "city_id": obj["CITY_ID"],
            "district": obj["DISTRICT_UA"],
            "city": obj["CITY_UA"]
        }
        result.append(City(**data))
    print(result)
    City.objects.bulk_create(result)


def get_offices():
    cities = City.objects.all()[:100]
    result = []
    offices_url = f"https://www.ukrposhta.ua/address-classifier-ws/get_postoffices_by_postcode_cityid_cityvpzid"
    r = requests.get(url=offices_url, headers=headers)
    xml_data = r.text
    data_dict = xmltodict.parse(xml_data)
    entries = data_dict["Entries"].get("Entry")
    if entries and isinstance(entries, list):
        # print(entries)
        for obj in entries:
            related_city = City.objects.filter(city_id=obj["CITY_ID"])
            print(related_city)
            if related_city.exists():
                data = {
                    "related_city": related_city.first(),
                    "post_office": obj["POSTOFFICE_UA"],
                    "post_code": obj["POSTCODE"],
                    "longitude": obj["LONGITUDE"],
                    "street": obj["STREET_UA_VPZ"],
                    "post_office_id": obj["POSTOFFICE_ID"],
                    "status": obj["LOCK_UA"],
                    "type": obj["TYPE_LONG"]
                }
                result.append(UkrOffice(**data))
    elif entries and isinstance(entries, dict):
        # print(entries)
        related_city = City.objects.filter(city_id=entries["CITY_ID"])
        if related_city.exists():
            data = {
                "related_city": related_city.first(),
                "post_office": entries["POSTOFFICE_UA"],
                "post_code": entries["POSTCODE"],
                "longitude": entries["LONGITUDE"],
                "street": entries["STREET_UA_VPZ"],
                "post_office_id": entries["POSTOFFICE_ID"],
                "status": entries["LOCK_UA"],
                "type": entries["TYPE_LONG"]
            }
            result.append(UkrOffice(**data))
    # print(result)
    UkrOffice.objects.bulk_create(result)


def get_office(city_id):
    try:
        city = City.objects.get(city_id=city_id)
        result = []
        print(city)
        offices_url = f"https://www.ukrposhta.ua/address-classifier-ws/get_postoffices_by_postcode_cityid_cityvpzid?city_id={city_id}"
        r = requests.get(url=offices_url, headers=headers)
        xml_data = r.text
        data_dict = xmltodict.parse(xml_data)
        entries = data_dict["Entries"].get("Entry")
        if entries and isinstance(entries, list):
            # print(entries)
            for obj in entries:
                data = {
                    # "related_city": city,
                    "post_office": obj["POSTOFFICE_UA"],
                    "post_code": obj["POSTCODE"],
                    "longitude": obj["LONGITUDE"],
                    "street": obj["STREET_UA_VPZ"],
                    "post_office_id": obj["POSTOFFICE_ID"],
                    "status": obj["LOCK_UA"],
                    "type": obj["TYPE_LONG"]
                }
                result.append(data)
        elif entries and isinstance(entries, dict):
            # print(entries)
            data = {
                # "related_city": city,
                "post_office": entries["POSTOFFICE_UA"],
                "post_code": entries["POSTCODE"],
                "longitude": entries["LONGITUDE"],
                "street": entries["STREET_UA_VPZ"],
                "post_office_id": entries["POSTOFFICE_ID"],
                "status": entries["LOCK_UA"],
                "type": entries["TYPE_LONG"]
            }
            result.append(data)
        # print(result)
        return result
    except:
        return None


# Convert dictionary to JSON
# json_data = json.dumps(data_dict, indent=4, ensure_ascii=False)
#
# # print(json_data)