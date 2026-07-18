from django.test import SimpleTestCase

from order.email_utils import format_delivery_line


class FormatDeliveryLineTests(SimpleTestCase):
    def test_no_duplicate_when_same(self):
        self.assertEqual(format_delivery_line("Ланівці", "Ланівці"), "Ланівці")

    def test_address_already_contains_city(self):
        self.assertEqual(
            format_delivery_line("Ланівці", "Ланівці, Відділення №1"),
            "Ланівці, Відділення №1",
        )

    def test_join_when_different(self):
        self.assertEqual(
            format_delivery_line("Київ", "Відділення №12"),
            "Київ, Відділення №12",
        )

    def test_empty(self):
        self.assertEqual(format_delivery_line("", ""), "—")
