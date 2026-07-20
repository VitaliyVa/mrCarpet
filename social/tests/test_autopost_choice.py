"""Tests: галочка «Опублікувати в соцмережах» на формі створення товару."""

from unittest.mock import patch

from django.test import TestCase, override_settings

from catalog.admin_forms import ProductAdminForm
from catalog.models import Product
from social.models import SocialSettings


class AutopostFormFieldTests(TestCase):
    def test_field_present_and_on_by_default_when_creating(self):
        form = ProductAdminForm()
        self.assertIn("post_to_socials", form.fields)
        self.assertTrue(form.fields["post_to_socials"].initial)

    def test_field_hidden_when_editing(self):
        product = Product.objects.create(title="Наявний килим")
        form = ProductAdminForm(instance=product)
        self.assertNotIn("post_to_socials", form.fields)

    def test_fieldsets_render_checkbox_only_on_add(self):
        """ProductAdmin має явні fieldsets — поле треба додати і туди."""
        from django.contrib import admin as dj_admin

        from catalog.admin import ProductAdmin

        model_admin = ProductAdmin(Product, dj_admin.site)
        request = None

        def has_field(fieldsets):
            return any(
                "post_to_socials" in (section[1].get("fields") or ())
                for section in fieldsets
            )

        self.assertTrue(has_field(model_admin.get_fieldsets(request, None)))
        product = Product.objects.create(title="Килим для редагування форми")
        self.assertFalse(has_field(model_admin.get_fieldsets(request, product)))


class AutopostSignalChoiceTests(TestCase):
    def setUp(self):
        s = SocialSettings.load()
        s.auto_post_new_products_tg = False
        s.auto_post_new_products_meta = False
        s.products_channel_id = "-100123"
        s.save()

    @patch("social.services.telegram_products.enqueue_product_channel_post")
    def test_checkbox_on_posts_even_if_global_toggle_off(self, mock_tg):
        product = Product(title="Новий килим")
        product._social_autopost_choice = True
        product.save()
        mock_tg.assert_called_once_with(product.pk)

    @patch("social.services.telegram_products.enqueue_product_channel_post")
    def test_checkbox_off_blocks_post_even_if_global_toggle_on(self, mock_tg):
        s = SocialSettings.load()
        s.auto_post_new_products_tg = True
        s.save()

        product = Product(title="Тихий килим")
        product._social_autopost_choice = False
        product.save()
        mock_tg.assert_not_called()

    @patch("social.services.telegram_products.enqueue_product_channel_post")
    def test_without_attr_falls_back_to_global_toggle(self, mock_tg):
        # створення поза адмінкою (імпорт/скрипт) — як було раніше
        s = SocialSettings.load()
        s.auto_post_new_products_tg = True
        s.save()

        product = Product.objects.create(title="Скриптовий килим")
        mock_tg.assert_called_once_with(product.pk)

    @patch("social.services.telegram_products.enqueue_product_channel_post")
    def test_editing_never_reposts(self, mock_tg):
        product = Product(title="Килим для редагування")
        product._social_autopost_choice = True
        product.save()
        mock_tg.reset_mock()

        # менеджер зайшов, змінив назву, зберіг — і навіть якщо атрибут лишився
        product.title = "Оновлена назва"
        product._social_autopost_choice = True
        product.save()
        mock_tg.assert_not_called()

    @override_settings(VIBER_AUTH_TOKEN="tok")
    @patch("social.services.viber_products.enqueue_product_viber_post")
    def test_checkbox_does_not_bypass_viber_master_switch(self, mock_viber):
        s = SocialSettings.load()
        s.viber_posting_enabled = False  # майстер-рубильник вимкнений
        s.save()

        product = Product(title="Viber килим")
        product._social_autopost_choice = True
        product.save()
        mock_viber.assert_not_called()

    @override_settings(VIBER_AUTH_TOKEN="tok")
    @patch("social.services.viber_products.enqueue_product_viber_post")
    def test_checkbox_posts_viber_when_master_switch_on(self, mock_viber):
        s = SocialSettings.load()
        s.viber_posting_enabled = True
        s.auto_post_new_products_viber = False
        s.save()

        product = Product(title="Viber килим 2")
        product._social_autopost_choice = True
        product.save()
        mock_viber.assert_called_once_with(product.pk)
