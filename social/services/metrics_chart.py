"""
The social-networks slide for the Telegram analytics album.

Answers what GA4 cannot: how many people *watched*. GA4 sees only those who
then came to the site, which for a rug video is a small fraction.

Layout is computed, never hand-placed. The first version positioned rows at
fixed offsets and the right-hand column overflowed the card the moment a
network name grew; every horizontal position here is derived from one of two
margins and every value is right-aligned to the second, so text cannot leave
the frame regardless of what the data says.
"""

from __future__ import annotations

import logging

from social.models import VideoDelivery

logger = logging.getLogger(__name__)

# Warm near-white rather than the older beige: at phone size the beige reads
# as a scan of a printed page.
BG = "#FBFAF8"
INK = "#14201C"
MUTED = "#8A8880"
FAINT = "#E8E4DC"
ACCENT = "#0E5A4A"

#: Opacity by rank rather than five different hues. One colour with a ramp
#: says "same thing, different amount"; five hues say "five different things".
RANK_ALPHA = (1.0, 0.72, 0.52, 0.38, 0.28)

LEFT = 0.075
RIGHT = 0.925


def _fmt(n) -> str:
    try:
        return f"{int(n or 0):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "0"


def render_social_chart(totals: dict[str, dict], *, days: int) -> bytes:
    import matplotlib

    matplotlib.use("Agg")
    import io

    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    labels = dict(VideoDelivery.Platform.choices)
    from social.services.video_metrics import silent_networks

    fig, ax = plt.subplots(figsize=(8.0, 10.0))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # ---- header -------------------------------------------------------
    ax.text(
        LEFT,
        0.955,
        "СОЦМЕРЕЖІ",
        transform=ax.transAxes,
        fontsize=9.5,
        color=ACCENT,
        fontweight="700",
        va="top",
    )
    ax.text(
        LEFT,
        0.928,
        f"Щоденне відео · останні {days} дн.",
        transform=ax.transAxes,
        fontsize=10.5,
        color=MUTED,
        va="top",
    )

    # Networks that report views sort first: a network we cannot measure is
    # not a network that performed badly.
    ranked = sorted(
        totals.items(),
        key=lambda kv: (1 if kv[1]["views_known"] else 0, kv[1]["views"]),
        reverse=True,
    )

    if not ranked:
        ax.text(
            0.5, 0.5, "Ще немає зібраних метрик", ha="center", color=MUTED, fontsize=12
        )
        return _png(fig, plt, io)

    total_views = sum(d["views"] for _, d in ranked if d["views_known"])
    peak = max((d["views"] for _, d in ranked if d["views_known"]), default=0) or 1

    # ---- headline -----------------------------------------------------
    ax.text(
        LEFT,
        0.878,
        _fmt(total_views),
        transform=ax.transAxes,
        fontsize=54,
        fontweight="700",
        color=INK,
        va="top",
    )
    ax.text(
        LEFT,
        0.792,
        "переглядів разом",
        transform=ax.transAxes,
        fontsize=11,
        color=MUTED,
        va="top",
    )

    # ---- rows ---------------------------------------------------------
    # The band is fixed; row height divides it. Adding a sixth network makes
    # the rows thinner rather than pushing the footnote off the canvas.
    silent = {k: v for k, v in silent_networks().items() if k not in totals}
    band_top, band_bottom = 0.735, 0.30
    slots = len(ranked) + (1 if silent else 0)
    row_h = (band_top - band_bottom) / max(slots, 1)

    y = band_top
    for i, (platform, data) in enumerate(ranked):
        centre = y - row_h / 2
        alpha = RANK_ALPHA[min(i, len(RANK_ALPHA) - 1)]

        ax.text(
            LEFT,
            centre + row_h * 0.22,
            labels.get(platform, platform),
            transform=ax.transAxes,
            fontsize=12.5,
            fontweight="600",
            color=INK,
            va="center",
        )

        # Right-aligned to the margin — this is what makes overflow
        # impossible rather than unlikely.
        if data["views_known"]:
            ax.text(
                RIGHT,
                centre + row_h * 0.22,
                _fmt(data["views"]),
                transform=ax.transAxes,
                fontsize=15,
                fontweight="700",
                color=INK,
                ha="right",
                va="center",
            )
        else:
            ax.text(
                RIGHT,
                centre + row_h * 0.22,
                "н/д",
                transform=ax.transAxes,
                fontsize=11,
                color=MUTED,
                ha="right",
                va="center",
            )

        track_y = centre - row_h * 0.10
        bar_h = 0.011
        ax.add_patch(
            FancyBboxPatch(
                (LEFT, track_y),
                RIGHT - LEFT,
                bar_h,
                boxstyle="round,pad=0,rounding_size=0.0055",
                transform=ax.transAxes,
                facecolor=FAINT,
                edgecolor="none",
                clip_on=False,
            )
        )
        if data["views_known"] and data["views"] > 0:
            width = (RIGHT - LEFT) * (data["views"] / peak)
            ax.add_patch(
                FancyBboxPatch(
                    (LEFT, track_y),
                    max(width, 0.02),
                    bar_h,
                    boxstyle="round,pad=0,rounding_size=0.0055",
                    transform=ax.transAxes,
                    facecolor=ACCENT,
                    alpha=alpha,
                    edgecolor="none",
                    clip_on=False,
                )
            )

        detail = f"{_fmt(data['likes'])} вподобань · {_fmt(data['comments'])} коментарів"
        if data["videos"]:
            detail += f" · {data['videos']} відео"
        ax.text(
            LEFT,
            track_y - row_h * 0.20,
            detail,
            transform=ax.transAxes,
            fontsize=9,
            color=MUTED,
            va="center",
        )
        y -= row_h

    # Named, not omitted: a missing row reads as a broken collector, a row
    # that explains itself reads as a known limit.
    if silent:
        for platform, reason in silent.items():
            ax.text(
                LEFT,
                y - row_h * 0.35,
                f"{labels.get(platform, platform)} — {reason}",
                transform=ax.transAxes,
                fontsize=8.5,
                color=MUTED,
                va="center",
            )
            y -= row_h * 0.22

    # ---- footnote -----------------------------------------------------
    ax.plot(
        [LEFT, RIGHT],
        [0.20, 0.20],
        transform=ax.transAxes,
        color=FAINT,
        linewidth=1.0,
    )
    note = [
        "Перегляд — хтось побачив відео у стрічці. Це не захід на сайт:",
        "GA4 бачить лише тих, хто перейшов далі.",
        "",
        "Скільки людей прийшло з кожної мережі на сайт — слайд",
        "«Звідки приходять», кампанія daily-video.",
    ]
    ny = 0.168
    for line in note:
        ax.text(LEFT, ny, line, transform=ax.transAxes, fontsize=9.5, color=MUTED, va="top")
        ny -= 0.026

    fig.text(LEFT, 0.028, "mr.Carpet", color=MUTED, fontsize=8, fontweight="600")
    return _png(fig, plt, io)


def _png(fig, plt, io) -> bytes:
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


def build_social_photo(*, days: int = 7) -> tuple[str, bytes] | None:
    """
    The album slide, or None when there is nothing to show.

    Never raises: this is one extra picture appended to a GA4 report, and a
    broken chart must not cost the user the ones that worked.
    """
    try:
        from social.services.video_metrics import weekly_summary

        totals = weekly_summary(days=days)
        if not totals:
            return None
        return ("08_social.png", render_social_chart(totals, days=days))
    except Exception as exc:
        logger.warning("social chart failed: %s", exc)
        return None
