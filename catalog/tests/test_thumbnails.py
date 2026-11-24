import io
import os
import shutil
import tempfile

from django.core.files.storage import FileSystemStorage
from django.db.models.fields.files import FieldFile
from django.template import Context, Template
from django.test import SimpleTestCase, override_settings
from PIL import Image

from catalog import thumbnails
from catalog.thumbnails import thumbnail_url


def _write(path, size=(1000, 800), fmt="PNG"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGB", size, (120, 80, 60)).save(path, format=fmt)


class ThumbnailUrlTests(SimpleTestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.override = override_settings(MEDIA_ROOT=self.root, MEDIA_URL="/media/")
        self.override.enable()
        self.addCleanup(self.override.disable)
        thumbnails._memo.clear()

    def test_creates_webp_on_first_use_and_reuses_it(self):
        _write(os.path.join(self.root, "articles", "cover.png"))
        url = thumbnail_url("articles/cover.png", 400)
        self.assertEqual(url, "/media/thumbs/w400/articles/cover.webp")
        out = os.path.join(self.root, "thumbs", "w400", "articles", "cover.webp")
        with Image.open(out) as im:
            self.assertEqual(im.format, "WEBP")
            self.assertEqual(im.size, (400, 320))
        mtime = os.stat(out).st_mtime
        thumbnails._memo.clear()
        self.assertEqual(thumbnail_url("articles/cover.png", 400), url)
        self.assertEqual(os.stat(out).st_mtime, mtime)

    def test_missing_file_falls_back_to_original(self):
        self.assertEqual(thumbnail_url("products/nope.webp", 240), "/media/products/nope.webp")

    def test_broken_image_falls_back_to_original(self):
        path = os.path.join(self.root, "products", "broken.webp")
        os.makedirs(os.path.dirname(path))
        with open(path, "wb") as fh:
            fh.write(b"not an image")
        self.assertEqual(thumbnail_url("products/broken.webp", 240), "/media/products/broken.webp")

    def test_small_webp_is_served_as_is(self):
        _write(os.path.join(self.root, "products", "small.webp"), size=(300, 300), fmt="WEBP")
        self.assertEqual(thumbnail_url("products/small.webp", 480), "/media/products/small.webp")

    def test_empty_field_and_svg(self):
        self.assertEqual(thumbnail_url("", 240), "")
        self.assertEqual(thumbnail_url(None, 240), "")
        self.assertEqual(thumbnail_url("icons/x.svg", 240), "/media/icons/x.svg")

    def test_field_file_and_template_filter(self):
        _write(os.path.join(self.root, "products", "additional", "a b.jpg"), fmt="JPEG")
        storage = FileSystemStorage(location=self.root, base_url="/media/")

        class _Field:
            storage = None

        f = _Field()
        f.storage = storage
        ff = FieldFile(None, f, "products/additional/a b.jpg")
        html = Template("{% load thumbnails %}{{ img|thumb:240 }}").render(Context({"img": ff}))
        self.assertEqual(html, "/media/thumbs/w240/products/additional/a%20b.webp")

    def test_regenerates_when_source_changes(self):
        src = os.path.join(self.root, "c.png")
        _write(src, size=(1000, 1000))
        thumbnail_url("c.png", 200)
        out = os.path.join(self.root, "thumbs", "w200", "c.webp")
        old = os.stat(out).st_mtime
        _write(src, size=(1000, 500))
        os.utime(src, (old + 10, old + 10))
        thumbnail_url("c.png", 200)
        with Image.open(out) as im:
            self.assertEqual(im.size, (200, 100))
