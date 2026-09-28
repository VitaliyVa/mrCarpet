"""Prom.ua / Rozetka YML feed."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from unittest import TestCase as PlainTestCase

from project.prom_feed import build_categories, build_offers, render_feed


class RenderFeedTests(PlainTestCase):
    def test_valid_xml_structure(self):
        categories = [
            {"id": 1, "name": "Килими", "parentId": None},
            {"id": 2, "name": "Турецькі", "parentId": 1},
        ]
        offers = [{
            "id": "1-2", "group_id": "1", "available": "true", "categoryId": 2,
            "price": 400, "currencyId": "UAH", "name": "Килим <A&B>",
            "vendor": "mr.Carpet", "description": "опис",
            "url": "https://mrcarpet24.com/catalog/product/x/",
            "pictures": ["https://mrcarpet24.com/media/a.jpg"],
            "params": [("Розмір", "120x200 см")],
        }]
        xml = render_feed(categories, offers)
        root = ET.fromstring(xml.encode("utf-8"))
        offer = root.find("shop/offers/offer")
        self.assertEqual(offer.get("available"), "true")
        self.assertEqual(offer.find("name").text, "Килим <A&B>")
        self.assertEqual(offer.find("param").text, "120x200 см")
        cats = root.findall("shop/categories/category")
        self.assertEqual(len(cats), 2)
        self.assertEqual(cats[1].get("parentId"), "1")
