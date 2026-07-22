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
import re
import subprocess
import time
from pathlib import Path

import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

logger = logging.getLogger(__name__)

MUSIC_DIR = "social/tiktok/music"
# Hand-picked tracks can be dropped into this directory too (any of these
# formats); ffmpeg reads them all. The rotation treats them the same as the
# generated ones.
TRACK_EXTENSIONS = (".wav", ".mp3", ".m4a", ".ogg")
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
    return sorted(
        f"{MUSIC_DIR}/{name}"
        for name in files
        if name.lower().endswith(TRACK_EXTENSIONS)
    )


def pick_track(seed: int | None = None) -> str:
    """
    Choose a track: round-robin by pick id.

    Deterministic, so a regenerated video keeps its music — and unlike the
    seeded-random choice this replaces, consecutive picks can never land on
    the same track (two days in a row of one melody is exactly what listeners
    notice, and what TikTok's reused-audio heuristics look at).

    Returns an empty string when the library is empty, so the montage can fall
    back to a silent bed rather than failing the whole run.
    """
    tracks = library_paths()
    if not tracks:
        return ""
    return tracks[(seed or 0) % len(tracks)]


def absolute_track_path(relative: str) -> str:
    return str(Path(settings.MEDIA_ROOT) / relative)


# ---------------------------------------------------------------------------
# Chorus finder: where to start a long track.
#
# Hand-picked tracks run 2+ minutes, and second 0 is usually the intro — the
# quietest, least recognisable part. The hook of the song is the loudest
# sustained stretch, so the montage should start there. No structural analysis
# is attempted: mean loudness over a montage-length window is a proxy that
# lands on the chorus or the drop for the kind of upbeat tracks this account
# posts, and it needs nothing beyond one ffmpeg decode pass.
# ---------------------------------------------------------------------------

# Windows shorter than this gain nothing from seeking: the generated 16s
# library must keep starting at 0, where its single musical idea begins.
MIN_SEEK_SURPLUS = 4.0

_RMS_LINE = re.compile(r"lavfi\.astats\.Overall\.RMS_level=(-?[\d.]+|-inf)")
_TIME_LINE = re.compile(r"pts_time:([\d.]+)")


def _rms_chunks(path: str) -> list[tuple[float, float]]:
    """(start_seconds, rms_db) per ~half-second of audio, via one ffmpeg pass."""
    out = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-i", path,
            "-af",
            # ~0.5s at 48k; other sample rates just give slightly different
            # chunk lengths, which is why times are read from pts, not assumed.
            "asetnsamples=n=24000,astats=metadata=1:reset=1,"
            "ametadata=mode=print:key=lavfi.astats.Overall.RMS_level:file=-",
            "-f", "null", "-",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    ).stdout

    chunks: list[tuple[float, float]] = []
    when = 0.0
    for line in out.splitlines():
        t = _TIME_LINE.search(line)
        if t:
            when = float(t.group(1))
            continue
        m = _RMS_LINE.search(line)
        if m:
            value = m.group(1)
            chunks.append((when, -90.0 if value == "-inf" else float(value)))
    return chunks


def _choose_offset(chunks: list[tuple[float, float]], duration: float) -> float:
    """
    The start of the loudest sustained window, nudged onto a quiet moment.

    The nudge matters for how the cut sounds: the loudest window's edge can
    fall mid-note, while a local dip just before it is the breath between
    phrases. Search is over chunk starts, so the result is deterministic.
    """
    if not chunks:
        return 0.0
    track_end = chunks[-1][0] + 0.5
    latest_start = track_end - duration - 0.5
    if latest_start <= 0:
        return 0.0

    candidates = [(t, db) for t, db in chunks if t <= latest_start]
    best_start, best_mean = 0.0, float("-inf")
    for start, _db in candidates:
        window = [db for t, db in chunks if start <= t < start + duration]
        mean = sum(window) / len(window) if window else float("-inf")
        if mean > best_mean:
            best_start, best_mean = start, mean

    # Snap to the quietest chunk within ±1.5s — the gap between phrases.
    near = [(db, t) for t, db in candidates if abs(t - best_start) <= 1.5]
    if near:
        best_start = min(near)[1]
    return round(best_start, 2)


def chorus_offset(path: str, duration: float) -> float:
    """
    Seconds into the track the montage's music should start. 0 means "from the
    top" — short tracks, unreadable files and analysis failures all land there,
    so the caller never has to care why.
    """
    try:
        chunks = _rms_chunks(path)
        if not chunks or chunks[-1][0] + 0.5 < duration + MIN_SEEK_SURPLUS:
            return 0.0
        offset = _choose_offset(chunks, duration)
        if offset:
            logger.info("music %s: starting at %.1fs (chorus window)", path, offset)
        return offset
    except Exception:
        logger.exception("chorus analysis failed for %s, starting at 0", path)
        return 0.0


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
