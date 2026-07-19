"""Tests: Product → Viber channel post + подвійний гейт."""

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from catalog.models import Product
from social.models import SocialSettings
from social.services import viber_products
from social.services.viber_products import (
    post_product_to_viber,
    viber_configured,
    viber_posting_enabled,
)


class ViberConfigTests(TestCase):
    @override_settings(VIBER_AUTH_TOKEN="")
    def test_not_configured_without_token(self):
        self.assertFalse(viber_configured())
        self.assertFalse(viber_posting_enabled())

    @override_settings(VIBER_AUTH_TOKEN="tok-123")
    def test_master_switch_off_by_default(self):
        # токен є, але рубильник у Social settings вимкнений
        self.assertTrue(viber_configured())
        self.assertFalse(viber_posting_enabled())

    @override_settings(VIBER_AUTH_TOKEN="tok-123")
    def test_enabled_with_token_and_switch(self):
        s = SocialSettings.load()
        s.viber_posting_enabled = True
        s.save()
        self.assertTrue(viber_posting_enabled())


@override_settings(VIBER_AUTH_TOKEN="tok-123")
class ViberPostTests(TestCase):
    def setUp(self):
        viber_products._superadmin_cache.clear()

    def _product(self):
        product = Product.objects.create(title="Viber килим")
        product.image.name = "photos/main.jpg"
        product.save(update_fields=["image"])
        return product

    @patch("social.services.viber_products.requests.post")
    def test_picture_post_payload(self, mock_post):
        account_resp = MagicMock()
        account_resp.content = b"x"
        account_resp.json.return_value = {
            "status": 0,
            "members": [{"id": "SA==", "role": "superadmin"}],
        }
        post_resp = MagicMock()
        post_resp.content = b"x"
        post_resp.json.return_value = {"status": 0, "status_message": "ok"}
        mock_post.side_effect = [account_resp, post_resp]

        result = post_product_to_viber(self._product())
        self.assertTrue(result["ok"])

        url, kwargs = mock_post.call_args_list[1][0][0], mock_post.call_args_list[1][1]
        self.assertTrue(url.endswith("/pa/post"))
        payload = kwargs["json"]
        self.assertEqual(payload["from"], "SA==")
        self.assertEqual(payload["type"], "picture")
        self.assertIn("Viber килим", payload["text"])
        self.assertIn("photos/main.jpg", payload["media"])
        self.assertEqual(
            kwargs["headers"]["X-Viber-Auth-Token"], "tok-123"
        )

    @patch("social.services.viber_products.requests.post")
    def test_api_error_reported(self, mock_post):
        account_resp = MagicMock()
        account_resp.content = b"x"
        account_resp.json.return_value = {
            "status": 0,
            "members": [{"id": "SA==", "role": "superadmin"}],
        }
        fail_resp = MagicMock()
        fail_resp.content = b"x"
        fail_resp.json.return_value = {"status": 2, "status_message": "invalidAuthToken"}
        mock_post.side_effect = [account_resp, fail_resp]

        result = post_product_to_viber(self._product())
        self.assertFalse(result["ok"])
        self.assertIn("invalidAuthToken", result["error"])

    @override_settings(VIBER_AUTH_TOKEN="")
    def test_no_token_short_circuit(self):
        result = post_product_to_viber(self._product())
        self.assertFalse(result["ok"])
        self.assertIn("VIBER_AUTH_TOKEN", result["error"])


class ViberSignalTests(TestCase):
    @patch("social.services.viber_products.enqueue_product_viber_post")
    def test_signal_silent_when_master_off(self, mock_enqueue):
        s = SocialSettings.load()
        s.viber_posting_enabled = False
        s.auto_post_new_products_viber = True
        s.save()
        Product.objects.create(title="Signal viber off")
        mock_enqueue.assert_not_called()

    @override_settings(VIBER_AUTH_TOKEN="tok-123")
    @patch("social.services.viber_products.enqueue_product_viber_post")
    def test_signal_fires_with_both_toggles(self, mock_enqueue):
        s = SocialSettings.load()
        s.viber_posting_enabled = True
        s.auto_post_new_products_viber = True
        s.save()
        product = Product.objects.create(title="Signal viber on")
        mock_enqueue.assert_called_once_with(product.pk)

    @override_settings(VIBER_AUTH_TOKEN="tok-123")
    @patch("social.services.viber_products.enqueue_product_viber_post")
    def test_signal_silent_without_auto_toggle(self, mock_enqueue):
        s = SocialSettings.load()
        s.viber_posting_enabled = True
        s.auto_post_new_products_viber = False
        s.save()
        Product.objects.create(title="Signal viber manual-only")
        mock_enqueue.assert_not_called()
