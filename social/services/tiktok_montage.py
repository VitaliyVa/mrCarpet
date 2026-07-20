"""
Assemble the final TikTok video from one generated clip.

Structure (~12s, inside the 11-18s window that performs best):

    0.0-2.2s  still frame + the price question
    2.2-3.4s  same still, dimmed, with a 3-2-1 countdown
    3.4-9.4s  the generated clip, price card sliding in
    9.4-12.0s frozen last frame + the comment prompt

Only the clip costs money; everything here is CPU. That is the whole point —
paying a video model for a longer render would buy what ffmpeg does for free.

Text carries the format: most of TikTok is watched muted, and overlays lift
conversion by about half again. It is kept inside the safe zone, clear of the
handle and caption at the top and the button rail at the bottom.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

OUT_W, OUT_H = 1080, 1920
FPS = 30

HOOK_SECONDS = 2.2
COUNT_SECONDS = 1.2  # 0.4s per digit
TAIL_SECONDS = 2.6

# TikTok covers the top ~120px with the handle/caption and the bottom ~450px
# with the like/share rail, so copy lives between these fractions of height.
SAFE_TOP = 0.16
SAFE_BOTTOM = 0.74

FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
)

FFMPEG_TIMEOUT_SEC = 600


class MontageError(RuntimeError):
    pass


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def font_path() -> str:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    raise MontageError(
        "No Cyrillic-capable font found — install fonts-dejavu-core"
    )


def _strip_emoji(text: str) -> str:
    """
    Drop emoji before drawing.

    DejaVu has no emoji glyphs, so anything outside its coverage renders as an
    empty box. Emoji stay in the caption, where TikTok renders them properly.
    """
    return "".join(ch for ch in (text or "") if ord(ch) < 0x2190).strip()


def _esc(text: str) -> str:
    """Escape for ffmpeg drawtext, which parses : ' \\ and % itself."""
    return (
        (text or "")
        .replace("\\", r"\\")
        .replace(":", r"\:")
        .replace("'", r"\'")
        .replace("%", r"\%")
    )


def _esc_path(path: str) -> str:
    """
    Escape a path for use inside a filter argument.

    ffmpeg splits filter options on ':', so a Windows drive letter breaks the
    filtergraph. Linux paths are unaffected, but dev runs on Windows.
    """
    return (path or "").replace("\\", "/").replace(":", r"\:")


def _run(args: list[str], label: str) -> None:
    proc = subprocess.run(
        args, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT_SEC
    )
    if proc.returncode != 0:
        tail = (proc.stderr or "")[-800:]
        raise MontageError(f"{label} failed: {tail}")


def _wrap(text: str, width: int) -> list[str]:
    """Wrap by words — drawtext has no line breaking of its own."""
    words = (text or "").split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def _drawtext_block(
    text: str,
    *,
    y_frac: float,
    size: int,
    font: str,
    wrap: int = 0,
    box: bool = True,
    enable: str = "",
) -> str:
    """One drawtext per line, stacked — keeps long copy inside the frame."""
    text = _strip_emoji(text)
    lines = _wrap(text, wrap) if wrap else [text]
    step = size * 1.35 / OUT_H
    return ",".join(
        _drawtext(
            line,
            y_frac=y_frac + i * step,
            size=size,
            font=font,
            box=box,
            enable=enable,
        )
        for i, line in enumerate(lines)
    )


def _drawtext(
    text: str,
    *,
    y_frac: float,
    size: int,
    font: str,
    box: bool = True,
    enable: str = "",
) -> str:
    parts = [
        f"fontfile='{_esc_path(font)}'",
        f"text='{_esc(text)}'",
        f"fontsize={size}",
        "fontcolor=white",
        "x=(w-text_w)/2",
        f"y=h*{y_frac:.4f}",
        "line_spacing=12",
    ]
    if box:
        # A slab behind the copy keeps it legible over any interior.
        parts += ["box=1", "boxcolor=black@0.55", "boxborderw=28"]
    if enable:
        parts.append(f"enable='{enable}'")
    return "drawtext=" + ":".join(parts)


def build_montage(clip_path: str, script: dict, out_path: str) -> str:
    """
    Render the finished video. `script` comes from tiktok_script.build_script.
    """
    if not ffmpeg_available():
        raise MontageError("ffmpeg/ffprobe not installed")

    clip = Path(clip_path)
    if not clip.exists():
        raise MontageError(f"clip not found: {clip}")

    font = font_path()
    scale = (
        f"scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease,"
        f"pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
    )

    with tempfile.TemporaryDirectory(prefix="tiktok-montage-") as tmpdir:
        tmp = Path(tmpdir)
        first = tmp / "first.png"
        last = tmp / "last.png"

        _run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(clip),
             "-vf", "select=eq(n\\,0)", "-frames:v", "1", str(first)],
            "extract first frame",
        )
        _run(
            ["ffmpeg", "-v", "error", "-y", "-sseof", "-0.2", "-i", str(clip),
             "-frames:v", "1", str(last)],
            "extract last frame",
        )

        # 1. Hook: the question over the opening still.
        hook = tmp / "hook.mp4"
        countdown_filters = "".join(
            ","
            + _drawtext(
                digit,
                y_frac=0.44,
                size=160,
                font=font,
                box=False,
                enable=f"between(t,{HOOK_SECONDS + i * 0.4:.2f},"
                f"{HOOK_SECONDS + (i + 1) * 0.4:.2f})",
            )
            for i, digit in enumerate(script["countdown"])
        )
        # The question clears the frame once the countdown starts, so the
        # viewer is looking at one thing at a time.
        hook_text = _drawtext_block(
            script["hook"],
            y_frac=SAFE_TOP,
            size=56,
            font=font,
            wrap=26,
            enable=f"lt(t,{HOOK_SECONDS})",
        )
        dim = (
            f"eq=brightness=-0.12:enable='gte(t,{HOOK_SECONDS})'"
        )
        _run(
            ["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", str(first),
             "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
             "-t", f"{HOOK_SECONDS + COUNT_SECONDS:.2f}",
             "-vf", f"{scale},{dim},{hook_text}{countdown_filters},fps={FPS}",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(hook)],
            "render hook",
        )

        # 2. Body: the generated clip with the price revealed.
        body = tmp / "body.mp4"
        price_text = _drawtext(
            script["price"], y_frac=SAFE_BOTTOM, size=112, font=font
        )
        size_text = _drawtext(
            script["size"], y_frac=SAFE_BOTTOM + 0.075, size=46, font=font
        )
        _run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(clip),
             "-vf", f"{scale},{price_text},{size_text},fps={FPS}",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000", str(body)],
            "render body",
        )

        # 3. Tail: frozen last frame with the comment prompt.
        tail = tmp / "tail.mp4"
        cta_text = _drawtext_block(
            script["cta"], y_frac=0.42, size=64, font=font, wrap=22
        )
        _run(
            ["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", str(last),
             "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
             "-t", f"{TAIL_SECONDS:.2f}",
             "-vf", f"{scale},{cta_text},fps={FPS}",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(tail)],
            "render tail",
        )

        # 4. Concat. Re-encoding here keeps timestamps sane across segments.
        listing = tmp / "concat.txt"
        listing.write_text(
            "".join(f"file '{p.as_posix()}'\n" for p in (hook, body, tail)),
            encoding="utf-8",
        )
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        _run(
            ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
             "-i", str(listing),
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
             "-movflags", "+faststart", str(out)],
            "concat segments",
        )

    logger.info("TikTok montage built: %s", out_path)
    return str(out_path)


def probe(path: str) -> dict:
    """Duration/dimensions of a rendered file, for tests and diagnostics."""
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,width,height:format=duration",
         "-of", "default=noprint_wrappers=1", str(path)],
        capture_output=True, text=True, timeout=60,
    )
    info: dict = {}
    for line in proc.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            info.setdefault(key, value)
    return info
