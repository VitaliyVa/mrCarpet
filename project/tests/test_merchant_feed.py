"""Google Merchant feed."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from unittest import TestCase as PlainTestCase

from django.test import TestCase

from project.merchant_feed import format_size, render_feed

G = "{http://base.google.com/ns/1.0}"


class FormatSizeTests(PlainTestCase):
    def test_metres_cyrillic(self):
        self.assertEqual(format_size("1.2х2.0"), "120x200 см")
        self.assertEqual(format_size("0.67х1.2"), "67x120 см")
        self.assertEqual(format_size("1.5x2.3"), "150x230 см")

    def test_passthrough(self):
        self.assertEqual(format_size("∅ 67 см"), "∅ 67 см")
        self.assertEqual(format_size(""), "")


class RenderFeedTests(PlainTestCase):
    def test_valid_xml_and_escaping(self):
        xml = render_feed([{
            "id": "1-2", "title": "Килим <A&B>", "price": "400.00 UAH",
            "sale_price": "", "additional_image_link": ["https://x/1.jpg", "https://x/2.jpg"],
        }])
        root = ET.fromstring(xml.encode("utf-8"))
        item = root.find("channel/item")
        self.assertEqual(item.find(f"{G}title").text, "Килим <A&B>")
        self.assertIsNone(item.find(f"{G}sale_price"))
        self.assertEqual(len(item.findall(f"{G}additional_image_link")), 2)


class FeedViewTests(TestCase):
    def test_endpoint(self):
        resp = self.client.get("/feeds/google-merchant.xml", secure=True)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("application/xml", resp["Content-Type"])
        ET.fromstring(resp.content)
