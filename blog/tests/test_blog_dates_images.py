"""
Blog dates for scheduled articles, cover thumbnails and the robots preview hint.

Scheduled articles are seeded (and their ``updated`` stamped by auto_now)
days or weeks before ``published_at``. Article JSON-LD, article:modified_time
and the sitemap lastmod used ``updated`` as is, so a post going live on
17 January claimed it was last modified in November, before it existed.

Cards, the article hero and the "related" aside rendered the original upload
(2+ MB PNG covers in 72 px slots); they now get resized WebP copies, while
og:image keeps the original for social previews.
"""

import json
import os
import re
import shutil
import tempfile
from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from blog.models import Article
from catalog import thumbnails
from project.seo_jsonld import article_modified_at
from project.sitemaps import ArticleSitemap

SITE = "https://mrcarpet24.com"


def _article_jsonld(html):
    for block in re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.S
    ):
        data = json.loads(block)
        if data.get("@type") == "Article":
            return data
    return None


def _robots(html):
    m = re.search(r'<meta name="robots" content="([^"]*)"', html)
    return m and m.group(1)


class ScheduledArticleDatesTests(TestCase):
    def setUp(self):
        # Seed migrations add real (scheduled) articles; they go live over
        # time and would change counts and ordering here.
        Article.objects.all().delete()
        now = timezone.now()
        # Seeded long ago, went live an hour ago: updated < published_at.
        self.published_at = now - timedelta(hours=1)
        self.seeded = Article.objects.create(
            title="Чистка килима снігом",
            status=Article.Status.PUBLISHED,
            published_at=self.published_at,
            description="<p>Текст.</p>",
        )
        self.stale_updated = now - timedelta(days=50)
        Article.objects.filter(pk=self.seeded.pk).update(updated=self.stale_updated)
        self.seeded.refresh_from_db()

        # Published long ago, edited yesterday: updated > published_at.
        self.edited_updated = now - timedelta(days=1)
        self.edited = Article.objects.create(
            title="Як прати килимок",
            status=Article.Status.PUBLISHED,
            published_at=now - timedelta(days=30),
            description="<p>Текст.</p>",
        )
        Article.objects.filter(pk=self.edited.pk).update(updated=self.edited_updated)
        self.edited.refresh_from_db()

        self.future = Article.objects.create(
            title="Модні килими 2027",
            status=Article.Status.PUBLISHED,
            published_at=now + timedelta(days=20),
            description="<p>Текст.</p>",
        )

    def test_helper_takes_the_later_date(self):
        self.assertEqual(article_modified_at(self.seeded), self.published_at)
        self.assertEqual(article_modified_at(self.edited), self.edited_updated)

    def test_helper_handles_missing_dates(self):
        self.assertIsNone(article_modified_at(Article(title="x")))
        draft = Article(title="x", updated=self.stale_updated)
        self.assertEqual(article_modified_at(draft), self.stale_updated)

    def test_jsonld_modified_is_not_before_published(self):
        html = self.client.get(self.seeded.get_absolute_url()).content.decode()
        data = _article_jsonld(html)
        self.assertIsNotNone(data)
        self.assertEqual(data["datePublished"], self.published_at.isoformat())
        self.assertEqual(data["dateModified"], self.published_at.isoformat())

    def test_jsonld_keeps_a_real_later_edit(self):
        html = self.client.get(self.edited.get_absolute_url()).content.decode()
        data = _article_jsonld(html)
        self.assertEqual(data["dateModified"], self.edited_updated.isoformat())

    def test_article_modified_time_meta_is_not_before_published(self):
        html = self.client.get(self.seeded.get_absolute_url()).content.decode()
        published = re.search(
            r'<meta property="article:published_time" content="([^"]*)"', html
        ).group(1)
        modified = re.search(
            r'<meta property="article:modified_time" content="([^"]*)"', html
        ).group(1)
        self.assertEqual(modified, published)

    def test_sitemap_lastmod_is_the_later_date(self):
        sitemap = ArticleSitemap()
        items = {a.pk: a for a in sitemap.items()}
        self.assertEqual(sitemap.lastmod(items[self.seeded.pk]), self.published_at)
        self.assertEqual(sitemap.lastmod(items[self.edited.pk]), self.edited_updated)

    def test_sitemap_lastmod_needs_no_extra_queries(self):
        """published_at is in .only(): no deferred-field query per URL."""
        sitemap = ArticleSitemap()
        with self.assertNumQueries(1):
            dates = [sitemap.lastmod(a) for a in sitemap.items()]
        self.assertEqual(len(dates), 2)

    @override_settings(SEO_INDEXING_ENABLED=True, SITE_URL=SITE)
    def test_sitemap_xml_dates_and_no_scheduled(self):
        xml = self.client.get("/sitemap.xml").content.decode()
        self.assertNotIn(self.future.slug, xml)
        block = re.search(
            r"<url><loc>[^<]*%s/</loc><lastmod>([^<]*)</lastmod>" % re.escape(self.seeded.slug),
            xml,
        )
        self.assertIsNotNone(block, xml)
        self.assertEqual(block.group(1), self.published_at.date().isoformat())

    def test_scheduled_article_appears_once_its_time_comes(self):
        later = timezone.now() + timedelta(days=21)
        self.assertIn(self.future, list(Article.objects.public(now=later)))
        self.assertNotIn(self.future, list(ArticleSitemap().items()))


@override_settings(SEO_INDEXING_ENABLED=True, SITE_URL=SITE)
class RobotsImagePreviewTests(TestCase):
    def test_indexable_article_allows_large_image_preview(self):
        article = Article.objects.create(
            title="Килим у вітальню",
            status=Article.Status.PUBLISHED,
            published_at=timezone.now() - timedelta(days=1),
        )
        html = self.client.get(article.get_absolute_url()).content.decode()
        self.assertEqual(
            _robots(html), "index, follow, max-image-preview:large, max-snippet:-1"
        )

    def test_search_stays_plain_noindex(self):
        html = self.client.get("/catalog/?q=test").content.decode()
        self.assertEqual(_robots(html), "noindex, follow")

    @override_settings(SEO_INDEXING_ENABLED=False)
    def test_indexing_off_stays_noindex_nofollow(self):
        html = self.client.get(reverse("blog")).content.decode()
        self.assertEqual(_robots(html), "noindex, nofollow")


class BlogCoverThumbnailTests(TestCase):
    COVER = "articles/test-cover.png"

    def setUp(self):
        from PIL import Image

        self.media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=self.media, MEDIA_URL="/media/")
        override.enable()
        self.addCleanup(override.disable)
        thumbnails._memo.clear()
        self.addCleanup(thumbnails._memo.clear)
        # Seeded articles would take the featured slot once they go live.
        Article.objects.all().delete()

        os.makedirs(os.path.join(self.media, "articles"))
        Image.new("RGB", (1536, 1024), (150, 110, 80)).save(
            os.path.join(self.media, self.COVER), format="PNG"
        )
        now = timezone.now()
        self.first = Article.objects.create(
            title="Килим у ванну",
            status=Article.Status.PUBLISHED,
            published_at=now - timedelta(hours=1),
            image=self.COVER,
            description="<p>Текст.</p>",
        )
        self.second = Article.objects.create(
            title="Килим на кухню",
            status=Article.Status.PUBLISHED,
            published_at=now - timedelta(hours=2),
            image=self.COVER,
            description="<p>Текст.</p>",
        )
        self.third = Article.objects.create(
            title="Килим у спальню",
            status=Article.Status.PUBLISHED,
            published_at=now - timedelta(hours=3),
            image=self.COVER,
            description="<p>Текст.</p>",
        )

    def _imgs(self, html):
        return re.findall(r"<img\b[^>]*>", html)

    def _original_in_img(self, html):
        return [tag for tag in self._imgs(html) if "/media/" + self.COVER in tag]

    def test_blog_list_uses_thumbnails_with_srcset(self):
        html = self.client.get(reverse("blog")).content.decode()
        self.assertEqual(self._original_in_img(html), [])
        featured = [t for t in self._imgs(html) if 'fetchpriority="high"' in t][0]
        self.assertIn('src="/media/thumbs/w800/articles/test-cover.webp"', featured)
        self.assertIn("/media/thumbs/w480/articles/test-cover.webp 480w", featured)
        self.assertIn("/media/thumbs/w1200/articles/test-cover.webp 1200w", featured)
        lazy = [t for t in self._imgs(html) if "test-cover" in t and 'loading="lazy"' in t]
        self.assertTrue(lazy)
        for tag in lazy:
            self.assertIn('src="/media/thumbs/w480/articles/test-cover.webp"', tag)
            self.assertIn("/media/thumbs/w800/articles/test-cover.webp 800w", tag)
        self.assertTrue(
            os.path.exists(
                os.path.join(self.media, "thumbs", "w480", "articles", "test-cover.webp")
            )
        )

    def test_article_page_uses_thumbnails_and_keeps_og_original(self):
        html = self.client.get(self.first.get_absolute_url()).content.decode()
        self.assertEqual(self._original_in_img(html), [])
        hero = [t for t in self._imgs(html) if 'fetchpriority="high"' in t][0]
        self.assertIn('src="/media/thumbs/w800/articles/test-cover.webp"', hero)
        self.assertIn("1200w", hero)
        self.assertIn('sizes="(max-width: 800px) calc(100vw - 40px), 860px"', hero)
        self.assertIn('width="1200" height="800"', hero)
        # Related aside: small copies, not the 1.5k px upload.
        self.assertIn('src="/media/thumbs/w240/articles/test-cover.webp"', html)
        # Social previews keep the original (WebP previews are flaky in messengers).
        og = re.search(r'<meta property="og:image" content="([^"]*)"', html).group(1)
        self.assertTrue(og.endswith("/media/" + self.COVER), og)
        tw = re.search(r'<meta name="twitter:image" content="([^"]*)"', html).group(1)
        self.assertTrue(tw.endswith("/media/" + self.COVER), tw)

    def test_unreadable_thumbnail_falls_back_to_original(self):
        """A broken upload still shows a picture instead of an empty slot."""
        with open(os.path.join(self.media, self.COVER), "wb") as fh:
            fh.write(b"not an image")
        thumbnails._memo.clear()
        html = self.client.get(reverse("blog")).content.decode()
        featured = [t for t in self._imgs(html) if 'fetchpriority="high"' in t][0]
        self.assertIn('src="/media/%s"' % self.COVER, featured)
