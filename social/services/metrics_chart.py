"""
The social-networks slide for the Telegram analytics album.

Deliberately borrows the private style primitives from project.ga4_charts
rather than restating the palette. This image is shown in the same album as
the seven GA4 slides, so it has to be the same object visually — a second
copy of the house style would drift on the first tweak and the odd one out
would be this one.

What it answers is the question GA4 cannot: how many people *watched*.
GA4 sees only those who then came to the site, which for a rug video is a
small fraction. The two are complementary and both appear in one album.
"""

from __future__ import annotations

import logging

from social.models import VideoDelivery

logger = logging.getLogger(__name__)

#: Colour per network, warm-to-cool in the house green. Assigned by name and
#: not by rank, so a network keeps its colour between weeks — a bar that
#: changes colour when it changes position is unreadable at a glance.
NETWORK_COLOURS = {
    VideoDelivery.Platform.INSTAGRAM: "#1B5F4F",
    VideoDelivery.Platform.YOUTUBE: "#2F7A68",
    VideoDelivery.Platform.FACEBOOK: "#4A9482",
    VideoDelivery.Platform.THREADS: "#6BAE9C",
    VideoDelivery.Platform.TIKTOK: "#8FC4B4",
}


def render_social_chart(totals: dict[str, dict], *, days: int) -> bytes:
    from project.ga4_charts import (
        BG,
        CARD,
        CONTENT_TOP,
        GRID,
        INK,
        MUTED,
        _blank_fig,
        _fig_bytes,
        _fmt_int,
        _glossary,
        _header,
    )
    from matplotlib.patches import FancyBboxPatch, Rectangle

    from social.services.video_metrics import silent_networks

    labels = dict(VideoDelivery.Platform.choices)
    fig, ax = _blank_fig()
    _header(
        ax,
        "8 · Соцмережі",
        f"Останні {days} дн. · скільки людей побачило щоденне відео",
    )

    # Views first, but networks that do not report views sort last rather than
    # as zero — otherwise Instagram used to look like the worst performer
    # purely because it was the one we could not measure.
    ranked = sorted(
        totals.items(),
        key=lambda kv: (1 if kv[1]["views_known"] else 0, kv[1]["views"]),
        reverse=True,
    )
    peak = max((d["views"] for _, d in ranked if d["views_known"]), default=0) or 1

    if not ranked:
        ax.text(
            0.5,
            0.55,
            "Ще немає зібраних метрик",
            ha="center",
            color=MUTED,
            fontsize=12,
        )
        _glossary(ax, ["Метрики збираються щодня о 04:00, після першої публікації."])
        _social_footer(fig)
        return _fig_bytes(fig)

    total_views = sum(d["views"] for _, d in ranked if d["views_known"])
    ax.text(
        0.05,
        CONTENT_TOP,
        _fmt_int(total_views),
        transform=ax.transAxes,
        fontsize=30,
        fontweight="700",
        color=INK,
        va="top",
    )
    ax.text(
        0.05,
        CONTENT_TOP - 0.055,
        "переглядів разом",
        transform=ax.transAxes,
        fontsize=10,
        color=MUTED,
        va="top",
    )

    y = CONTENT_TOP - 0.11
    for platform, data in ranked:
        ax.add_patch(
            FancyBboxPatch(
                (0.05, y - 0.075),
                0.90,
                0.085,
                boxstyle="round,pad=0.008,rounding_size=0.012",
                transform=ax.transAxes,
                facecolor=CARD,
                edgecolor=GRID,
                clip_on=False,
            )
        )
        ax.text(
            0.075,
            y - 0.012,
            labels.get(platform, platform),
            transform=ax.transAxes,
            fontsize=10.5,
            fontweight="600",
            color=INK,
            va="center",
        )

        if data["views_known"]:
            width = 0.52 * (data["views"] / peak)
            ax.add_patch(
                Rectangle(
                    (0.075, y - 0.045),
                    max(width, 0.004),
                    0.016,
                    transform=ax.transAxes,
                    facecolor=NETWORK_COLOURS.get(platform, "#8FC4B4"),
                    edgecolor="none",
                    clip_on=False,
                )
            )
            ax.text(
                0.075 + max(width, 0.004) + 0.012,
                y - 0.037,
                f"{_fmt_int(data['views'])} 👁",
                transform=ax.transAxes,
                fontsize=9,
                fontweight="600",
                color=INK,
                va="center",
            )
        else:
            ax.text(
                0.075,
                y - 0.037,
                "перегляди не надаються",
                transform=ax.transAxes,
                fontsize=8.5,
                color=MUTED,
                va="center",
            )

        detail = f"{_fmt_int(data['likes'])} ❤   {_fmt_int(data['comments'])} 💬"
        if data["videos"]:
            detail += f"   ·   {data['videos']} відео"
        ax.text(
            0.62,
            y - 0.012,
            detail,
            transform=ax.transAxes,
            fontsize=8.5,
            color=MUTED,
            va="center",
        )
        y -= 0.105

    # Named, not omitted: a missing row reads as a broken collector, while a
    # row that explains itself reads as a known limit.
    for platform, reason in silent_networks().items():
        if platform in totals:
            continue
        ax.text(
            0.075,
            y - 0.02,
            f"{labels.get(platform, platform)} — {reason}",
            transform=ax.transAxes,
            fontsize=8,
            color=MUTED,
            va="center",
        )
        y -= 0.035

    _glossary(
        ax,
        [
            "Перегляд — хтось побачив відео у стрічці. Це не те саме, "
            "що захід на сайт: GA4 бачить лише тих, хто перейшов далі.",
            "Хто саме прийшов на сайт із кожної мережі — дивись слайд "
            "«Звідки приходять», кампанія daily-video.",
        ],
    )
    _social_footer(fig)
    return _fig_bytes(fig)


def _social_footer(fig) -> None:
    from project.ga4_charts import FOOT_Y, MUTED

    fig.text(
        0.05,
        FOOT_Y,
        "mr.Carpet · Instagram · YouTube · Facebook · Threads · TikTok",
        color=MUTED,
        fontsize=7.5,
    )


def build_social_photo(*, days: int = 7) -> tuple[str, bytes] | None:
    """
    The album slide, or None when there is nothing to show.

    Never raises: this is one extra picture appended to a GA4 report, and a
    broken chart must not cost the user the six that worked.
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
