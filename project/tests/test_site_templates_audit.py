"""
Site-wide template fixes from the November audit.

* mobile menu links pointed at "#"
* hub pages (home, collection, blog list) had titles nobody searches for,
  and /blog/?page=2 repeated page 1's title
* ?page=N on a page that does not paginate declared itself canonical
* customer-facing titles used long dashes
* the FAQ promised wool and cotton rugs the shop does not sell
* category page: "13 товари", breadcrumbs missing «Каталог», identical
  alts on every gallery photo
"""

import re
from datetime import timedelta

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from blog.models import Article
from blog.views import PER_PAGE
from catalog.models import (
    Product,
    ProductAttribute,
    ProductCategory,
    ProductImage,
    Size,
)
from catalog.templatetags.catalog_filters import plural_uk, plural_uk_form
from project.seo_jsonld import get_faq_items

SITE = "https://mrcarpet24.com"
DASHES = ("—", "–")


def _canonical(html):
    m = re.search(r'<link rel="canonical" href="([^"]*)"', html)
    return m and m.group(1)


def _og_url(html):
    m = re.search(r'<meta property="og:url" content="([^"]*)"', html)
    return m and m.group(1)


def _title(html):
    m = re.search(r"<title>(.*?)</title>", html, re.S)
    return m and m.group(1).strip()


def _description(html):
    m = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', html)
    return m and m.group(1)


def _h1(html):
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    return m and re.sub(r"\s+", " ", m.group(1)).strip()


class PluralUkTests(SimpleTestCase):
    FORMS = "товар,товари,товарів"

    def test_forms(self):
        cases = {
            0: "товарів",
            1: "товар",
            2: "товари",
            4: "товари",
            5: "товарів",
            11: "товарів",
            12: "товарів",
            14: "товарів",
            21: "товар",
            22: "товари",
            65: "товарів",
            99: "товарів",
            101: "товар",
            111: "товарів",
        }
        for n, word in cases.items():
            self.assertEqual(plural_uk(n, self.FORMS), word, n)

    def test_junk_falls_back_to_many(self):
        self.assertEqual(plural_uk_form(None, self.FORMS), "товарів")
        self.assertEqual(plural_uk_form("x", ("a", "b", "c")), "c")


class FaqCopyTests(SimpleTestCase):
    def test_no_wool_or_cotton_promised(self):
        text = " ".join(q + " " + a for q, a in get_faq_items()).lower()
        for word in ("вовн", "бавовн"):
            self.assertNotIn(word, text)
        self.assertIn("поліпропілен", text)

    def test_no_long_dashes(self):
        for q, a in get_faq_items():
            for dash in DASHES:
                self.assertNotIn(dash, q)
                self.assertNotIn(dash, a)


@override_settings(SEO_INDEXING_ENABLED=True, SITE_URL=SITE)
class SitePagesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cat = ProductCategory.objects.create(title="Турецькі", slug="turetski")
        size = Size.objects.create(title="1.6 x 2.3")
        # 13 buyable products: 2 pages of 12, and "13 товарів"
        for i in range(13):
            p = Product.objects.create(title=f"Килим {i}", slug=f"kylym-audit-{i}")
            ProductAttribute.objects.create(
                product=p, size=size, price=1000 + i, quantity=3
            )
            p.categories.add(cls.cat)
        # Discounted: lowest price is 1012 * 0.5 = 506
        ProductAttribute.objects.filter(product__slug="kylym-audit-12").update(
            discount=50
        )
        # Out of stock and cheaper: must not become the "від" price
        oos = Product.objects.create(title="Килим OOS", slug="kylym-audit-oos")
        ProductAttribute.objects.create(product=oos, size=size, price=100, quantity=0)
        ProductAttribute.objects.create(product=oos, size=size, price=2000, quantity=1)
        cls.product = Product.objects.get(slug="kylym-audit-0")
        for n in range(3):
            ProductImage.objects.create(
                product=cls.product, image=f"products/additional/a{n}.jpg", sort_order=n
            )

    def get(self, url, status=200):
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status, url)
        return resp.content.decode()

    # --- mobile menu links --------------------------------------------------
    def test_mobile_menu_links_are_real(self):
        html = self.get("/")
        block = html.split('<div class="header_info__block">', 1)[1].split(
            '<div class="header_payment_info">', 1
        )[0]
        self.assertNotIn('href="#"', block)
        for name in ("about", "blog", "faq", "delivery", "refund", "terms", "policy", "stock"):
            self.assertIn(f'href="{reverse(name)}"', block, name)
        self.assertIn('data-href="contacts-modal"', block)

    def test_register_consent_links_are_real(self):
        html = self.get("/")
        info = html.split('<div class="register-modal__form-info">', 1)[1].split("</div>", 1)[0]
        self.assertNotIn('href="#"', info)
        self.assertIn(f'href="{reverse("policy")}"', info)
        self.assertIn(f'href="{reverse("terms")}"', info)

    # --- hub titles ---------------------------------------------------------
    def test_home_h1_says_what_is_sold(self):
        self.assertEqual(_h1(self.get("/")), "Килими з доставкою по Україні")

    def test_collection_title_and_description(self):
        html = self.get("/catalog/collection/")
        self.assertEqual(
            _title(html), "Купити килим: усі моделі з цінами і розмірами | mr.Carpet"
        )
        desc = _description(html)
        self.assertIn("14 моделей", desc)
        self.assertIn("від 506 грн", desc)
        self.assertLessEqual(len(desc), 170)
        self.assertEqual(_h1(html), "Вся колекція килимів")
        html2 = self.get("/catalog/collection/?page=2")
        self.assertIn("розмірами, сторінка 2 | mr.Carpet", _title(html2))

    def test_blog_title_and_pages(self):
        now = timezone.now()
        for i in range(PER_PAGE + 1):
            Article.objects.create(
                title=f"Стаття {i}",
                status=Article.Status.PUBLISHED,
                published_at=now - timedelta(days=i + 1),
                description="<p>Текст.</p>",
            )
        html = self.get("/blog/")
        self.assertEqual(
            _title(html), "Поради про килими: як вибрати і доглядати | Блог mr.Carpet"
        )
        self.assertEqual(_og_url(html), f"{SITE}/blog/")
        html2 = self.get("/blog/?page=2")
        self.assertIn(", сторінка 2 | Блог mr.Carpet", _title(html2))
        self.assertEqual(_canonical(html2), f"{SITE}/blog/?page=2")
        self.assertEqual(_og_url(html2), _canonical(html2))

    # --- ?page on pages that do not paginate --------------------------------
    def test_page_param_on_static_pages_points_to_clean_url(self):
        for path in ("/", "/about/", "/faq/", self.product.get_absolute_url()):
            html = self.get(f"{path}?page=2")
            self.assertEqual(_canonical(html), f"{SITE}{path}", path)
            self.assertEqual(_og_url(html), f"{SITE}{path}", path)

    def test_category_page_two_still_self_canonical(self):
        url = self.cat.get_absolute_url()
        self.assertEqual(_canonical(self.get(url + "?page=2")), f"{SITE}{url}?page=2")

    # --- long dashes in titles ----------------------------------------------
    def test_default_and_404_titles_have_no_long_dash(self):
        # The cart has no title of its own, so it shows the _base default.
        html = self.get(reverse("cart"))
        self.assertEqual(_title(html), "mr.Carpet: інтернет-магазин килимів")
        for prop in ('property="og:title"', 'name="twitter:title"'):
            m = re.search(r"<meta " + prop + r' content="([^"]*)"', html)
            self.assertEqual(m.group(1), "mr.Carpet: інтернет-магазин килимів", prop)
        html404 = self.get("/no-such-page-audit/", status=404)
        for dash in DASHES:
            self.assertNotIn(dash, _title(html404))

    def test_faq_page_has_no_wool(self):
        html = self.get("/faq/").lower()
        self.assertNotIn("вовн", html)
        self.assertNotIn("бавовн", html)

    # --- category template details ------------------------------------------
    def test_category_count_word_and_breadcrumbs(self):
        html = self.get(self.cat.get_absolute_url())
        self.assertIn("13 товарів", html)
        self.assertNotIn("13 товари", html)
        crumbs = html.split('<div class="bread-crumbs">', 1)[1].split("</div>", 1)[0]
        self.assertIn(f'href="{reverse("catalog")}"', crumbs)
        self.assertIn(">Каталог<", crumbs)

    def test_collection_count_word(self):
        self.assertIn("14 товарів", self.get("/catalog/collection/"))

    def test_gallery_alts_are_distinct(self):
        html = self.get(self.product.get_absolute_url())
        slider = html.split('<div class="product_slider_main swiper">', 1)[1].split(
            'class="product_slider_main', 1
        )[0]
        alts = re.findall(r'alt="(Килим 0[^"]*)"', slider)
        self.assertEqual(alts[:3], ["Килим 0", "Килим 0, фото 2", "Килим 0, фото 3"])
