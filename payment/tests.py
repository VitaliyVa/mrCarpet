from django.conf import settings
from django.test import TestCase, override_settings

from payment.models import LiqPaySettings
from payment.utils import get_liqpay_keys


class LiqPaySettingsKeysTests(TestCase):
    @override_settings(LIQPAY_PUBLIC_KEY="env_pub", LIQPAY_PRIVATE_KEY="env_priv")
    def test_falls_back_to_env(self):
        public, private = get_liqpay_keys()
        self.assertEqual(public, "env_pub")
        self.assertEqual(private, "env_priv")

    @override_settings(LIQPAY_PUBLIC_KEY="env_pub", LIQPAY_PRIVATE_KEY="env_priv")
    def test_admin_overrides_env(self):
        LiqPaySettings.objects.create(
            public_key="admin_pub",
            private_key="admin_priv",
        )
        public, private = get_liqpay_keys()
        self.assertEqual(public, "admin_pub")
        self.assertEqual(private, "admin_priv")

    def test_singleton_add(self):
        LiqPaySettings.objects.create(public_key="a", private_key="b")
        LiqPaySettings.objects.create(public_key="c", private_key="d")
        self.assertEqual(LiqPaySettings.objects.count(), 1)
