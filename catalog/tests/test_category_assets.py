"""
Category pages must not hold their first paint on a third-party host.

noUiSlider's stylesheet was a plain <link rel="stylesheet"> to cdn.jsdelivr.net
in <head>: every category and /catalog/collection/ waited for DNS + TLS to a
second host before drawing anything, for a widget that only exists after the
slider script runs at DOMContentLoaded. The scripts were parser-blocking too.
"""

import re

from django.test import TestCase

from catalog.models import Product, ProductAttribute, ProductCategory, Size

CDN_CSS = "https://cdn.jsdelivr.net/npm/nouislider@15.7.0/dist/nouislider.min.css"
CDN_JS = "https://cdn.jsdelivr.net/npm/nouislider@15.7.0/dist/nouislider.min.js"


def _strip_noscript(html):
    return re.sub(r"<noscript>.*?</noscript>", "", html, flags=re.S)


class CategorySliderAssetsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cat = ProductCategory.objects.create(title="Турецькі", slug="turetski-assets")
        size = Size.objects.create(title="1.6 x 2.3")
        for i, price in enumerate((900, 2500)):
            p = Product.objects.create(title=f"Килим {i}", slug=f"kylym-assets-{i}")
            ProductAttribute.objects.create(product=p, size=size, price=price, quantity=2)
            p.categories.add(cls.cat)

    def pages(self):
        for url in (self.cat.get_absolute_url(), "/catalog/collection/"):
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200, url)
            yield url, resp.content.decode()

    def test_price_slider_is_on_the_page(self):
        """Guard for the tests below: the slider markup really renders."""
        for url, html in self.pages():
            self.assertIn('id="price-slider"', html, url)

    def test_slider_css_is_not_render_blocking(self):
        for url, html in self.pages():
            live = _strip_noscript(html)
            blocking = re.findall(r'<link[^>]*rel="stylesheet"[^>]*cdn\.jsdelivr\.net[^>]*>', live)
            self.assertEqual(blocking, [], url)
            self.assertIn(
                f'<link rel="preload" as="style" href="{CDN_CSS}" '
                "onload=\"this.onload=null;this.rel='stylesheet'\" />",
                html,
                url,
            )
            # without JS the slider never exists, but keep the CSS for parity
            self.assertIn(f'<noscript><link rel="stylesheet" href="{CDN_CSS}" /></noscript>', html, url)

    def test_preconnect_matches_no_cors_requests(self):
        """A crossorigin preconnect opens a CORS connection the no-cors
        stylesheet and script would not reuse."""
        for url, html in self.pages():
            self.assertIn('<link rel="preconnect" href="https://cdn.jsdelivr.net" />', html, url)

    def test_slider_and_bundle_are_deferred_in_order(self):
        for url, html in self.pages():
            slider = html.index(f'<script src="{CDN_JS}" defer></script>')
            bundle = html.index(
                '<script src="/static/source/pages/catalog_inside/index.js?v=', slider
            )
            bundle_tag = html[bundle : html.index("</script>", bundle)]
            self.assertIn(" defer>", bundle_tag, url)
            # the slider is created on DOMContentLoaded, which runs after deferred scripts
            create = html.index("noUiSlider.create(", bundle)
            listener = html.rindex("document.addEventListener('DOMContentLoaded'", 0, create)
            self.assertGreater(listener, bundle, url)

    def test_price_inputs_hold_valid_numbers(self):
        """Ukrainian number format gave min="200,0": not a valid
        <input type="number"> value, so the inputs came up empty and the slider
        fell back to a 0..10000 range instead of the real prices."""
        for url, html in self.pages():
            for input_id in ("price_min_input", "price_max_input"):
                tag = re.search(rf'<input type="number" id="{input_id}"[^>]*>', html, re.S).group(0)
                attrs = dict(re.findall(r'(min|max|value)="([^"]*)"', tag))
                self.assertEqual(set(attrs), {"min", "max", "value"}, tag)
                for name, raw in attrs.items():
                    self.assertNotIn(",", raw, (url, input_id, name))
                    float(raw)
                self.assertEqual(float(attrs["min"]), 900, tag)
                self.assertEqual(float(attrs["max"]), 2500, tag)

    def test_missing_slider_library_does_not_break_filters(self):
        for url, html in self.pages():
            self.assertIn("priceMaxInput && window.noUiSlider)", html, url)
