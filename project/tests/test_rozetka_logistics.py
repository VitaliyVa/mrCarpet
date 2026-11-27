from django.test import SimpleTestCase

from project.rozetka_logistics import logistics, product_kind

MIRA = {"Основа": "Джут", "Висота ворсу": "6.5 мм", "Матеріал": "Поліпропілен"}


class RozetkaLogisticsTests(SimpleTestCase):
    def test_mira_close_to_published_weights_with_margin(self):
        # published: 80x150 1.78 kg, 160x230 5.59 kg, 200x300 9.12 kg
        for size, real in (("80x150 см", 1.78), ("160x230 см", 5.59), ("200x300 см", 9.12)):
            ship = logistics("Килим прямокутний Mira 24058/160 сірий", size, MIRA)
            self.assertGreaterEqual(ship["weight_kg"], real)
            self.assertLessEqual(ship["weight_kg"], real * 1.25)

    def test_roll_length_is_short_side(self):
        ship = logistics("Килим Mira 24058/160", "200x300 см", MIRA)
        self.assertEqual(ship["roll_length_cm"], 203)
        self.assertEqual(ship["package"][2], 203)
        self.assertTrue(ship["package_text"].endswith("x2.03 м"))
        self.assertEqual(ship["weight_text"], f"{ship['weight_kg']:.1f} кг")

    def test_rubber_backed_mats_roll_solid_rubber_flat(self):
        params = {"Основа": "Гума", "Матеріал": "Поліпропілен", "Висота ворсу": "Безворсовий"}
        ship = logistics("Килим прямокутний Flex 1952-M91 коричневий", "67x120 см", params)
        self.assertEqual(ship["package"][2], 70)  # rolled along the long side
        bath = logistics("Килим прямокутний для ванни Taflan", "60x100 см",
                         {"Основа": "Гума", "Висота ворсу": "6.5 мм"})
        self.assertEqual(bath["package"][2], 63)
        rubber = logistics("Килим напівкруглий під двері гумовий", "40x60 см",
                           {"Основа": "Гума", "Матеріал": "Гума"})
        self.assertEqual(rubber["package"], (3, 40, 60))
        self.assertEqual(rubber["package_text"], "0.03x0.4x0.6 м")

    def test_kinds(self):
        self.assertEqual(product_kind("Килим овальний Fantasy Grey", MIRA)[0], 2.6)
        self.assertEqual(product_kind("Килим напівкруглий під двері гумовий", {"Матеріал": "Гума", "Основа": "Гума"})[0], 5.0)
        self.assertEqual(product_kind("Килим La Rosa G1163", {"Висота ворсу": "10 мм", "Основа": "Джут"})[0], 2.1)
        self.assertEqual(product_kind("Килим дитячий Місто", {"Висота ворсу": "4 мм", "Основа": "Джут"})[0], 1.2)

    def test_round_and_unknown_size(self):
        self.assertIsNotNone(logistics("Килим круглий Teppich Smile", "∅ 67 см", MIRA))
        self.assertIsNone(logistics("Килим", "нестандартний", MIRA))
