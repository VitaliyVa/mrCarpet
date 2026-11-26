"""Resized WebP copies of uploaded images, created lazily on first render.

Uploads under /media are full-size originals (product gallery shots up to
~800 KB, article covers in PNG at 2+ MB) that templates used to put straight
into 120 px thumbnails and 376 px cards. ``thumbnail_url(field, width)``
returns the URL of a WebP no wider than ``width`` and writes it on first use:

    media/thumbs/v<THUMBS_VERSION>/w<width>/<original path without extension>.webp

so existing media on prod gets thumbnails without a management command, and
deleting ``media/thumbs`` is always safe (they are rebuilt on demand).

Any failure — missing file, unreadable image, read-only disk — falls back to
the original URL: a heavy picture is better than a broken one.
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading
from pathlib import PurePosixPath

from django.conf import settings

logger = logging.getLogger(__name__)

THUMBS_DIR = "thumbs"
# Bump when the encoding below changes. The version is part of the URL, so
# browsers (media is cached 30 days) and the on-disk cache both pick up the
# new files without anyone deleting media/thumbs by hand. Old versions are
# never read again and can be removed at any time. Stays under thumbs/ so
# the deploy's `chmod -R a+rX /app/media/thumbs` still covers it.
#   v1 (no segment): quality 80, method 4
#   v2: quality 72, method 6 (lighter files, slower encode, once per file)
THUMBS_VERSION = 2
DEFAULT_QUALITY = 72
# WebP effort 0..6. 6 is the slowest and smallest; it runs once per file.
WEBP_METHOD = 6
# Pillow decodes the whole frame; refuse absurd inputs instead of eating RAM.
MAX_SOURCE_PIXELS = 40_000_000

_lock = threading.Lock()
# Process-local memo: (name, width) -> (source mtime, url). Saves the two
# stat() calls per image on hot pages; a re-upload changes mtime and misses.
_memo: dict[tuple[str, int], tuple[float, str]] = {}
_MEMO_LIMIT = 20_000


def _thumb_name(name: str, width: int) -> str:
    stem = str(PurePosixPath(name.replace("\\", "/")).with_suffix(""))
    return f"{THUMBS_DIR}/v{THUMBS_VERSION}/w{width}/{stem}.webp"


def _media_url(name: str) -> str:
    base = settings.MEDIA_URL or "/media/"
    if not base.startswith(("/", "http://", "https://")):
        base = "/" + base
    if not base.endswith("/"):
        base += "/"
    from urllib.parse import quote

    return base + quote(name.replace("\\", "/"))


def _render(src_path: str, dst_path: str, width: int, quality: int) -> bool:
    """Write the resized WebP. Returns False when a copy is pointless."""
    from PIL import Image, ImageOps

    with Image.open(src_path) as img:
        if img.width * img.height > MAX_SOURCE_PIXELS:
            return False
        # Small WebP already: re-encoding would only lose quality.
        if img.width <= width and (img.format or "").upper() == "WEBP":
            return False
        img.draft("RGB", (width, width * 4))  # JPEG: decode at reduced scale
        img = ImageOps.exif_transpose(img)
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
        elif img.mode != "RGB":
            img = img.convert("RGB")
        if img.width > width:
            height = max(1, round(img.height * width / img.width))
            img = img.resize((width, height), Image.Resampling.LANCZOS)

        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        fd, tmp = tempfile.mkstemp(suffix=".webp", dir=os.path.dirname(dst_path))
        try:
            with os.fdopen(fd, "wb") as fh:
                img.save(fh, format="WEBP", quality=quality, method=WEBP_METHOD)
            # mkstemp creates 0600; nginx reads media as another user, so a
            # private file is served as 403 (broke every thumbnail on prod).
            os.chmod(tmp, 0o644)
            os.replace(tmp, dst_path)  # atomic: concurrent workers never see half a file
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    return True


def thumbnail_url(field, width: int, quality: int = DEFAULT_QUALITY) -> str:
    """URL of a ``width``-px-wide WebP of ``field`` (an ImageField value).

    Accepts a FieldFile or a plain media-relative name. Returns "" for an
    empty field and the original URL whenever a thumbnail cannot be made.
    """
    if not field:
        return ""
    name = getattr(field, "name", None) or str(field)
    try:
        width = int(width)
    except (TypeError, ValueError):
        width = 0
    try:
        original = field.url if hasattr(field, "url") else _media_url(name)
    except Exception:
        original = _media_url(name)
    if width <= 0 or not name or name.lower().endswith((".svg", ".gif")):
        return original

    try:
        media_root = os.fspath(settings.MEDIA_ROOT)
        src_path = os.path.join(media_root, name)
        src_mtime = os.stat(src_path).st_mtime
    except (OSError, ValueError):
        return original

    key = (name, width)
    hit = _memo.get(key)
    if hit and hit[0] == src_mtime:
        return hit[1]

    thumb = _thumb_name(name, width)
    dst_path = os.path.join(media_root, thumb)
    url = original
    try:
        try:
            fresh = os.stat(dst_path).st_mtime >= src_mtime
        except OSError:
            fresh = False
        if fresh:
            url = _media_url(thumb)
        else:
            with _lock:
                if _render(src_path, dst_path, width, quality):
                    url = _media_url(thumb)
    except Exception as exc:  # never break a page over a picture
        # Memoised below too, so a broken upload is not retried on every render.
        logger.warning("thumbnail failed for %s w=%s: %r", name, width, exc)
        url = original

    if len(_memo) >= _MEMO_LIMIT:
        _memo.clear()
    _memo[key] = (src_mtime, url)
    return url
