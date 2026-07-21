"""
One visual language for every chart we send to Telegram.

Extracted because there are eight slides in one album and they have to read
as one object. Before this, each renderer restated its own spacing and
colours, and the album drifted apart slide by slide.

Two rules everything here follows:

* **Positions are derived, never typed.** Every x comes from LEFT or RIGHT,
  every row height from dividing a band by the row count. Hand-placed offsets
  are what let text run off the edge the moment a label grew.
* **Values are right-aligned to the margin.** That is what makes overflow
  impossible rather than merely unlikely.
"""

from __future__ import annotations

import io
import logging
import os
import textwrap
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

logger = logging.getLogger(__name__)

FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")

#: Inter ships with the repo rather than the image. The container has only
#: matplotlib's bundled DejaVu Sans — a 2004 typeface whose wide letterforms
#: are most of what made these charts look dated, and no amount of layout
#: fixes that. Shipping the file avoids a Docker rebuild on every deploy.
FAMILY = "Inter"


def _register_fonts() -> str:
    try:
        found = False
        for name in os.listdir(FONT_DIR):
            if name.lower().endswith((".ttf", ".otf")):
                font_manager.fontManager.addfont(os.path.join(FONT_DIR, name))
                found = True
        if not found:
            return "DejaVu Sans"
        # Cyrillic is the whole point here; a font that cannot draw Ukrainian
        # would render tofu across every label.
        return FAMILY
    except Exception as exc:  # pragma: no cover - depends on the filesystem
        logger.warning("chart fonts unavailable, falling back: %s", exc)
        return "DejaVu Sans"


ACTIVE_FAMILY = _register_fonts()
plt.rcParams["font.family"] = ACTIVE_FAMILY
plt.rcParams["axes.unicode_minus"] = False

# ---- tokens -----------------------------------------------------------

BG = "#FBFAF8"
INK = "#14201C"
MUTED = "#8A8880"
FAINT = "#E8E4DC"
ACCENT = "#0E5A4A"
GOLD = "#B8954A"
WARN = "#B4553F"

#: Opacity by rank rather than a different hue per bar. One colour with a
#: ramp says "same thing, different amount"; five hues say "five different
#: things", which is a claim the data does not make.
RANK_ALPHA = (1.0, 0.72, 0.52, 0.38, 0.28, 0.22)

W, H = 8.0, 10.0
LEFT = 0.075
RIGHT = 0.925

#: Where the body may live. Below FOOT_TOP belongs to the footnote, above
#: BAND_TOP to the header — renderers that respect these cannot collide.
BAND_TOP = 0.735
BAND_BOTTOM = 0.30
FOOT_TOP = 0.20


def canvas():
    fig, ax = plt.subplots(figsize=(W, H))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    return fig, ax


def png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(
        buf,
        format="png",
        dpi=180,
        facecolor=fig.get_facecolor(),
        bbox_inches="tight",
        pad_inches=0.18,
    )
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def fmt_int(raw: Any) -> str:
    try:
        return f"{int(round(float(raw or 0))):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "0"


def fmt_money(raw: Any) -> str:
    return fmt_int(raw)


def fmt_pct(part: float, whole: float) -> str:
    if not whole:
        return "0%"
    return f"{100.0 * part / whole:.0f}%"


def eyebrow(ax, kicker: str, subtitle: str) -> None:
    """Small caps label plus one line of context. Replaces the old boxed
    title: at phone size a rule under a heading is chrome, not structure."""
    ax.text(
        LEFT, 0.955, kicker.upper(), transform=ax.transAxes,
        fontsize=9.5, color=ACCENT, fontweight="bold", va="top",
    )
    ax.text(
        LEFT, 0.928, subtitle, transform=ax.transAxes,
        fontsize=10.5, color=MUTED, va="top",
    )


def headline(ax, value: str, caption: str, *, y: float = 0.878) -> None:
    """The one number the slide exists to deliver."""
    ax.text(
        LEFT, y, value, transform=ax.transAxes,
        fontsize=54, fontweight="bold", color=INK, va="top",
    )
    ax.text(
        LEFT, y - 0.086, caption, transform=ax.transAxes,
        fontsize=11, color=MUTED, va="top",
    )


def track(ax, y: float, *, height: float = 0.011) -> None:
    _rounded(ax, LEFT, y, RIGHT - LEFT, height, FAINT, 1.0)


def bar(ax, y: float, fraction: float, *, rank: int = 0, height: float = 0.011,
        colour: str = ACCENT) -> None:
    width = (RIGHT - LEFT) * max(0.0, min(fraction, 1.0))
    _rounded(
        ax, LEFT, y, max(width, 0.02), height, colour,
        RANK_ALPHA[min(rank, len(RANK_ALPHA) - 1)],
    )


def _rounded(ax, x, y, w, h, colour, alpha) -> None:
    ax.add_patch(
        FancyBboxPatch(
            (x, y), w, h,
            boxstyle=f"round,pad=0,rounding_size={h / 2}",
            transform=ax.transAxes, facecolor=colour, alpha=alpha,
            edgecolor="none", clip_on=False,
        )
    )


def row_label(ax, y: float, left_text: str, right_text: str, *,
              right_muted: bool = False) -> None:
    """Name on the left, number right-aligned to the margin."""
    ax.text(
        LEFT, y, left_text, transform=ax.transAxes,
        fontsize=12.5, fontweight="semibold", color=INK, va="center",
    )
    ax.text(
        RIGHT, y, right_text, transform=ax.transAxes,
        fontsize=11 if right_muted else 15,
        fontweight="normal" if right_muted else "bold",
        color=MUTED if right_muted else INK,
        ha="right", va="center",
    )


def sub_label(ax, y: float, text: str) -> None:
    ax.text(
        LEFT, y, text, transform=ax.transAxes,
        fontsize=9, color=MUTED, va="center",
    )


def footnote(ax, lines: list[str], *, source: str = "mr.Carpet") -> None:
    """
    Plain-language explainer. A hairline and small text instead of the old
    filled box: the box took a fifth of the image to say something optional.
    """
    ax.plot(
        [LEFT, RIGHT], [FOOT_TOP, FOOT_TOP], transform=ax.transAxes,
        color=FAINT, linewidth=1.0,
    )
    y = FOOT_TOP - 0.032
    for line in lines:
        if not line:
            y -= 0.014
            continue
        for wrapped in textwrap.wrap(line, width=64) or [""]:
            ax.text(
                LEFT, y, wrapped, transform=ax.transAxes,
                fontsize=9.5, color=MUTED, va="top",
            )
            y -= 0.026
            if y < 0.05:
                return
    ax.figure.text(LEFT, 0.028, source, color=MUTED, fontsize=8, fontweight="semibold")


def empty(ax, message: str) -> None:
    ax.text(0.5, 0.5, message, ha="center", color=MUTED, fontsize=12)


def rows_band(count: int) -> float:
    """Row height that always fits: more rows get thinner, never longer."""
    return (BAND_TOP - BAND_BOTTOM) / max(count, 1)
