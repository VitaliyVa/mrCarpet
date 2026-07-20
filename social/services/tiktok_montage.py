"""
Assemble the final TikTok video from one generated clip.

Structure (~14.5s, inside the 11-18s window that performs best):

    0.0-5.0s   opening still: the price question, then a 3-2-1 countdown
    5.0-11.0s  the generated clip; the price lands 1.5s in, after a beat
    11.0-14.5s the clip's tail played backwards, with the comment prompt

Only the clip costs money; everything here is CPU. Paying a video model for a
longer render would buy exactly what ffmpeg does for free.

Video and audio are built separately and muxed at the end. Per-segment audio
would leave silence wherever a segment is a still frame, and concatenating
separately encoded audio tends to click at the joins.

Text carries the format — most of TikTok is watched muted — so every caption
fades in rather than snapping on, and sits inside the safe zone clear of the
handle at the top and the button rail at the bottom.
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

COUNT_START = 0.8
COUNT_STEP = 1.33          # three digits span 4s, a beat slower than a metronome
HOOK_SECONDS = 5.0         # countdown ends at 4.79, then a breath before the cut
PRICE_DELAY = 1.5          # hold the clip before answering, so the guess lands
REVERSE_SECONDS = 3.5

FADE = 0.35
BOX_BORDER = 16
LINE_STEP = 1.70  # multiples of font size; below this the plates overlap

SAFE_TOP = 0.16
SAFE_BOTTOM = 0.72

MUSIC_GAIN = "0.62"
TICK_GAIN = "0.95"  # must sit clearly above the music bed
TICK_FREQS = (880, 880, 1320)  # the rising third reads as a resolution

FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
)

FFMPEG_TIMEOUT_SEC = 900


class MontageError(RuntimeError):
    pass


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def font_path() -> str:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    raise MontageError("No Cyrillic-capable font found — install fonts-dejavu-core")


def _strip_emoji(text: str) -> str:
    """
    Drop emoji before drawing.

    DejaVu carries no emoji glyphs, so anything past its coverage renders as an
    empty box. Emoji stay in the caption, where TikTok renders them properly.
    """
    return "".join(ch for ch in (text or "") if ord(ch) < 0x2190).strip()


def _esc(text: str) -> str:
    """Escape for drawtext, which parses : ' \\ and % itself."""
    return (
        (text or "")
        .replace("\\", r"\\")
        .replace(":", r"\:")
        .replace("'", r"\'")
        .replace("%", r"\%")
    )


def _esc_path(path: str) -> str:
    """
    Escape a path used inside a filter argument.

    ffmpeg splits filter options on ':', so a Windows drive letter would break
    the filtergraph. Linux paths are unaffected, but development runs on Windows.
    """
    return (path or "").replace("\\", "/").replace(":", r"\:")


def _expr(text: str) -> str:
    """Commas inside an expression must be escaped or they end the option."""
    return text.replace(",", r"\,")


def _fade_in(start: float, duration: float = FADE) -> str:
    """alpha ramp 0 -> 1, so captions arrive instead of snapping on."""
    end = start + duration
    return "alpha='" + _expr(
        f"if(lt(t,{start:.2f}),0,if(lt(t,{end:.2f}),(t-{start:.2f})/{duration:.2f},1))"
    ) + "'"


def _fade_in_out(start: float, hold: float, duration: float = 0.22) -> str:
    """Ramp up, hold, ramp down — used for the countdown digits."""
    up_end = start + duration
    down_start = start + hold - duration
    end = start + hold
    return "alpha='" + _expr(
        f"if(lt(t,{start:.2f}),0,"
        f"if(lt(t,{up_end:.2f}),(t-{start:.2f})/{duration:.2f},"
        f"if(lt(t,{down_start:.2f}),1,"
        f"if(lt(t,{end:.2f}),({end:.2f}-t)/{duration:.2f},0))))"
    ) + "'"


def _drift_y(base: str, start: float, rise: int = 26, duration: float = 0.45) -> str:
    """
    Ease the text upwards as it fades in.

    An animated `fontsize` would give a nicer pop, but a time-varying font size
    segfaults ffmpeg (0xC0000005) — it re-rasterises the face every frame. A
    moving y expression is evaluated the same way and is stable, so the motion
    comes from position instead of scale.
    """
    end = start + duration
    return "y='" + _expr(
        f"({base})+{rise}*(1-min(1,max(0,(t-{start:.2f})/{duration:.2f})))"
    ) + "'"


def _wrap(text: str, width: int) -> list[str]:
    """Wrap by words — drawtext has no line breaking, and its \\n draws tofu."""
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


def _caption(
    text: str,
    *,
    y_frac: float,
    size: int,
    font: str,
    wrap: int = 0,
    appear_at: float | None = None,
) -> str:
    """
    A wrapped caption drawn one line at a time.

    Each line carries its own plate; LINE_STEP keeps consecutive plates from
    overlapping, which would otherwise show as a darker band across the seam.
    """
    lines = _wrap(_strip_emoji(text), wrap) if wrap else [_strip_emoji(text)]
    step_px = size * LINE_STEP
    parts = []
    for i, line in enumerate(lines):
        base_y = f"h*{y_frac:.4f}+{i * step_px:.0f}"
        options = [
            f"fontfile='{_esc_path(font)}'",
            f"text='{_esc(line)}'",
            f"fontsize={size}",
            "fontcolor=white",
            "x=(w-text_w)/2",
            "box=1",
            "boxcolor=black@0.55",
            f"boxborderw={BOX_BORDER}",
        ]
        if appear_at is None:
            options.append(f"y={base_y}")
        else:
            # Lines land in sequence, so the block assembles instead of
            # appearing all at once.
            start = appear_at + i * 0.12
            options.append(_drift_y(base_y, start))
            options.append(_fade_in(start))
        parts.append("drawtext=" + ":".join(options))
    return ",".join(parts)


def _run(args: list[str], label: str) -> None:
    proc = subprocess.run(
        args, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=FFMPEG_TIMEOUT_SEC,
    )
    if proc.returncode != 0:
        raise MontageError(f"{label} failed: {(proc.stderr or '')[-800:]}")


def probe(path: str) -> dict:
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


def clip_duration(path: str) -> float:
    return float(probe(path).get("duration") or 0)


def _scale() -> str:
    return (
        f"scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=decrease,"
        f"pad={OUT_W}:{OUT_H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
    )


def _build_audio(out: Path, *, duration: float, music_path: str) -> Path:
    """
    One continuous bed: music across the whole video plus a tick per digit.

    Silence is used when the library is empty so a missing track degrades the
    video rather than failing the night's run.
    """
    ticks = []
    for i, freq in enumerate(TICK_FREQS):
        at_ms = int((COUNT_START + i * COUNT_STEP) * 1000)
        ticks.append(
            f"sine=frequency={freq}:duration=0.18,"
            f"afade=t=out:st=0.02:d=0.16,"
            f"volume={TICK_GAIN},"
            f"adelay={at_ms}|{at_ms}[tick{i}]"
        )

    if music_path:
        # Duck the bed while the countdown runs, otherwise a loud bar of music
        # buries the ticks and the beat loses its punctuation.
        duck_from = max(COUNT_START - 0.25, 0)
        duck_to = COUNT_START + len(TICK_FREQS) * COUNT_STEP + 0.25
        music_in = ["-stream_loop", "-1", "-i", music_path]
        music_chain = (
            f"[0:a]atrim=0:{duration:.2f},asetpts=N/SR/TB,"
            f"volume={MUSIC_GAIN},"
            f"volume=0.45:enable='between(t\\,{duck_from:.2f}\\,{duck_to:.2f})',"
            f"afade=t=in:st=0:d=0.8,"
            f"afade=t=out:st={max(duration - 1.0, 0):.2f}:d=1.0[music]"
        )
    else:
        music_in = ["-f", "lavfi", "-i",
                    f"anullsrc=channel_layout=stereo:sample_rate=48000:d={duration:.2f}"]
        music_chain = "[0:a]anull[music]"

    lavfi_ticks = ";".join(ticks)
    tick_labels = "".join(f"[tick{i}]" for i in range(len(TICK_FREQS)))
    graph = (
        f"{music_chain};{lavfi_ticks};"
        f"[music]{tick_labels}amix=inputs={1 + len(TICK_FREQS)}:"
        f"duration=first:dropout_transition=0:normalize=0[out]"
    )

    _run(
        ["ffmpeg", "-v", "error", "-y", *music_in,
         "-filter_complex", graph, "-map", "[out]",
         "-t", f"{duration:.2f}", "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
         str(out)],
        "build audio bed",
    )
    return out


def build_montage(clip_path: str, script: dict, out_path: str, *, music_path: str = "") -> str:
    """Render the finished video. `script` comes from tiktok_script.build_script."""
    if not ffmpeg_available():
        raise MontageError("ffmpeg/ffprobe not installed")
    clip = Path(clip_path)
    if not clip.exists():
        raise MontageError(f"clip not found: {clip}")

    font = font_path()
    scale = _scale()
    source_seconds = clip_duration(str(clip))
    reverse_from = max(source_seconds - REVERSE_SECONDS, 0)
    reverse_len = min(REVERSE_SECONDS, source_seconds)

    with tempfile.TemporaryDirectory(prefix="tiktok-montage-") as tmpdir:
        tmp = Path(tmpdir)
        first = tmp / "first.png"
        _run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(clip),
             "-vf", "select=eq(n\\,0)", "-frames:v", "1", str(first)],
            "extract first frame",
        )

        # 1. Opening still: the question, then the countdown over the top of it.
        hook = tmp / "hook.mp4"
        question = _caption(
            script["hook"], y_frac=SAFE_TOP, size=56, font=font, wrap=26,
            appear_at=0.2,
        )
        digits = ",".join(
            "drawtext=" + ":".join([
                f"fontfile='{_esc_path(font)}'",
                f"text='{digit}'",
                "fontsize=190",
                "fontcolor=white",
                "x=(w-text_w)/2",
                "shadowcolor=black@0.6",
                "shadowx=4",
                "shadowy=4",
                _drift_y("(h-text_h)/2", COUNT_START + i * COUNT_STEP, rise=34),
                _fade_in_out(COUNT_START + i * COUNT_STEP, COUNT_STEP),
            ])
            for i, digit in enumerate(script["countdown"])
        )
        _run(
            ["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", str(first),
             "-t", f"{HOOK_SECONDS:.2f}",
             "-vf", f"{scale},{question},{digits},fps={FPS}",
             "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
             "-pix_fmt", "yuv420p", str(hook)],
            "render hook",
        )

        # 2. The clip itself, with the answer.
        body = tmp / "body.mp4"
        price = _caption(
            script["price"], y_frac=SAFE_BOTTOM, size=112, font=font,
            appear_at=PRICE_DELAY,
        )
        size_line = _caption(
            script["size"], y_frac=SAFE_BOTTOM + 0.085, size=46, font=font,
            appear_at=PRICE_DELAY + 0.22,
        )
        _run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(clip),
             "-vf", f"{scale},{price},{size_line},fps={FPS}",
             "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
             "-pix_fmt", "yuv420p", str(body)],
            "render body",
        )

        # 3. Tail: the end of the clip played backwards, so the picture keeps
        # moving instead of freezing on a still while the prompt is read.
        tail = tmp / "tail.mp4"
        cta = _caption(
            script["cta"], y_frac=0.42, size=64, font=font, wrap=22,
            appear_at=0.3,
        )
        _run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(clip),
             "-vf", (
                 f"trim=start={reverse_from:.2f},setpts=PTS-STARTPTS,reverse,"
                 f"{scale},{cta},fps={FPS}"
             ),
             "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
             "-pix_fmt", "yuv420p", str(tail)],
            "render reversed tail",
        )

        # 4. Concatenate the picture, then lay one continuous audio bed over it.
        silent = tmp / "silent.mp4"
        listing = tmp / "concat.txt"
        listing.write_text(
            "".join(f"file '{p.as_posix()}'\n" for p in (hook, body, tail)),
            encoding="utf-8",
        )
        _run(
            ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
             "-i", str(listing), "-an",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
             "-pix_fmt", "yuv420p", str(silent)],
            "concat segments",
        )

        total = HOOK_SECONDS + source_seconds + reverse_len
        audio = _build_audio(tmp / "bed.m4a", duration=total, music_path=music_path)

        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        _run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(silent), "-i", str(audio),
             "-map", "0:v:0", "-map", "1:a:0", "-shortest",
             "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
             "-movflags", "+faststart", str(out)],
            "mux audio",
        )

    logger.info("TikTok montage built: %s (%.1fs)", out_path, total)
    return str(out_path)
