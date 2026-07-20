"""
Background music library for the TikTok montage.

Third-party tracks are not an option: Content ID mutes or strikes repeated
commercial use, and the Content Posting API cannot reach TikTok's own library.
Royalty-free sites mostly need attribution and cannot be fetched automatically.

So the library is generated once with a music model and stored as files. The
licence is ours, no attribution is owed, and each track is unique — which also
matters because TikTok flags accounts that reuse one identical audio bed every
single day. Generation is a one-off; the daily job only picks a file.
"""

from __future__ import annotations

import logging
import random
import time
from pathlib import Path

import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

logger = logging.getLogger(__name__)

MUSIC_DIR = "social/tiktok/music"
# Community models need an explicit version; the bare name returns 404.
MODEL = (
    "meta/musicgen:"
    "671ac645ce5e552cc63a54a2bbff63fcf798043055d2dac5fc9e36a837eedcfb"
)
TRACK_SECONDS = 16  # a little longer than the montage, so it never runs dry

# Upbeat but not shouty: the bed should carry momentum through a 14 second
# clip without fighting the countdown ticks or the price reveal.
PROMPTS = (
    "upbeat modern pop instrumental, bright plucks, light claps, positive energy",
    "feel-good house groove, warm bass, catchy synth hook, steady four-on-the-floor",
    "energetic lo-fi hip hop beat, punchy drums, warm keys, confident and modern",
    "bright indie pop instrumental, rhythmic guitar, handclaps, sunny and upbeat",
    "modern commercial background track, driving beat, uplifting synth, catchy",
    "funky nu-disco instrumental, groovy bass line, crisp drums, danceable",
    "cheerful electronic pop, bouncy arpeggio, tight percussion, energetic mood",
    "confident trap-pop instrumental, crisp hats, warm melody, stylish and modern",
)


class MusicError(RuntimeError):
    pass


def library_paths() -> list[str]:
    """Stored track paths, sorted for a stable rotation order."""
    try:
        _dirs, files = default_storage.listdir(MUSIC_DIR)
    except (FileNotFoundError, OSError):
        return []
    return sorted(f"{MUSIC_DIR}/{name}" for name in files if name.endswith(".wav"))


def pick_track(seed: int | None = None) -> str:
    """
    Choose a track. Seeded by the pick id so a regenerated video keeps its music.

    Returns an empty string when the library has not been generated yet, so the
    montage can fall back to a silent bed rather than failing the whole run.
    """
    tracks = library_paths()
    if not tracks:
        return ""
    return random.Random(seed or 0).choice(tracks)


def absolute_track_path(relative: str) -> str:
    return str(Path(settings.MEDIA_ROOT) / relative)


def generate_library(count: int = 8, *, overwrite: bool = False) -> list[str]:
    """
    Generate the track library. Intended to be run once, by hand.

    Not part of the daily job: music is a fixed asset, and paying for it every
    night would be pure waste.
    """
    token = (getattr(settings, "REPLICATE_API_TOKEN", "") or "").strip()
    if not token:
        raise MusicError("REPLICATE_API_TOKEN empty")
    try:
        import replicate
    except ImportError as exc:  # pragma: no cover
        raise MusicError("replicate package not installed") from exc

    existing = library_paths()
    if existing and not overwrite:
        logger.info("TikTok music library already has %s tracks", len(existing))
        return existing

    # Clear first: default_storage.save() renames rather than replaces, so
    # regenerating over an existing library would leave both copies behind and
    # skew the rotation towards whichever prompts got duplicated.
    for path in existing:
        try:
            default_storage.delete(path)
        except Exception:
            logger.exception("could not delete %s", path)

    client = replicate.Client(api_token=token)
    created: list[str] = []
    for index in range(count):
        # Cycle the prompts and vary the seed, so the library can grow past the
        # number of prompts: same mood, a different melody each time. More
        # tracks means fewer repeats per cycle, and TikTok pays attention to
        # accounts that post the same audio every day.
        prompt = PROMPTS[index % len(PROMPTS)]
        logger.info("musicgen %s/%s: %s", index + 1, count, prompt[:50])
        started = time.monotonic()
        output = client.run(
            MODEL,
            input={
                "prompt": prompt,
                "duration": TRACK_SECONDS,
                "model_version": "stereo-large",
                "output_format": "wav",
                "normalization_strategy": "loudness",
                "seed": 1000 + index,
            },
        )
        url = getattr(output, "url", None) or (
            output[0] if isinstance(output, list) else output
        )
        blob = requests.get(str(url), timeout=300)
        blob.raise_for_status()
        path = default_storage.save(
            f"{MUSIC_DIR}/track-{index + 1:02d}.wav", ContentFile(blob.content)
        )
        created.append(path)
        logger.info("  saved %s in %.1fs", path, time.monotonic() - started)

    return created
