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

    def _ok_resp(self, payload=None):
        resp = MagicMock()
        resp.content = b"x"
        resp.json.return_value = payload or {"status": 0, "status_message": "ok"}
        return resp

    def _account_resp(self):
        return self._ok_resp(
            {"status": 0, "members": [{"id": "SA==", "role": "superadmin"}]}
        )

    @patch("social.services.viber_products.requests.post")
    def test_picture_post_payload(self, mock_post):
        account_resp = self._account_resp()
        post_resp = self._ok_resp()
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
    @patch(
        "social.services.telegram_products._product_photo_urls",
        return_value=[
            "https://mrcarpet24.com/media/a.jpg",
            "https://mrcarpet24.com/media/b.jpg",
            "https://mrcarpet24.com/media/c.jpg",
        ],
    )
    def test_extra_photos_sent_before_main(self, _urls, mock_post):
        mock_post.side_effect = [
            self._account_resp(),  # get_account_info
            self._ok_resp(),  # друге фото (без тексту)
            self._ok_resp(),  # третє фото (без тексту)
            self._ok_resp(),  # головне фото з описом — останнє
        ]
        result = post_product_to_viber(self._product())
        self.assertTrue(result["ok"])
        self.assertEqual(result["extra_photos"], 2)

        # спершу додаткові фото без тексту
        first_extra = mock_post.call_args_list[1][1]["json"]
        self.assertEqual(first_extra["text"], "")
        self.assertEqual(first_extra["media"], "https://mrcarpet24.com/media/b.jpg")
        second_extra = mock_post.call_args_list[2][1]["json"]
        self.assertEqual(second_extra["media"], "https://mrcarpet24.com/media/c.jpg")
        # останнім — головне фото з описом
        main_payload = mock_post.call_args_list[3][1]["json"]
        self.assertIn("Viber килим", main_payload["text"])
        self.assertEqual(main_payload["media"], "https://mrcarpet24.com/media/a.jpg")

    @patch("social.services.viber_products.requests.post")
    @patch(
        "social.services.telegram_products._product_photo_urls",
        return_value=[
            "https://mrcarpet24.com/media/a.jpg",
            "https://mrcarpet24.com/media/b.jpg",
        ],
    )
    def test_extra_photo_failure_does_not_fail_post(self, _urls, mock_post):
        mock_post.side_effect = [
            self._account_resp(),
            self._ok_resp({"status": 12, "status_message": "rate limit"}),  # доп. фото
            self._ok_resp(),  # головне фото з описом усе одно йде
        ]
        result = post_product_to_viber(self._product())
        self.assertTrue(result["ok"])
        self.assertEqual(result["extra_photos"], 0)

    @patch("social.services.viber_products.requests.post")
    def test_api_error_reported(self, mock_post):
        account_resp = self._account_resp()
        fail_resp = self._ok_resp({"status": 2, "status_message": "invalidAuthToken"})
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
