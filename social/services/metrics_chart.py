"""
The social-networks slide for the Telegram analytics album.

Answers what GA4 cannot: how many people *watched*. GA4 sees only those who
then came to the site, which for a rug video is a small fraction.

Built on project.chart_style like the seven GA4 slides rather than on its own
palette — eight pictures arriving in one album have to read as one document.
"""

from __future__ import annotations

import logging

from social.models import VideoDelivery

logger = logging.getLogger(__name__)


def render_social_chart(totals: dict[str, dict], *, days: int) -> bytes:
    from project.chart_style import (
        BAND_TOP,
        LEFT,
        MUTED,
        bar,
        canvas,
        empty,
        eyebrow,
        fmt_int,
        footnote,
        headline,
        png,
        row_label,
        rows_band,
        sub_label,
        track,
    )

    from social.services.video_metrics import silent_networks

    labels = dict(VideoDelivery.Platform.choices)
    fig, ax = canvas()
    eyebrow(ax, "Соцмережі", f"Щоденне відео · останні {days} дн.")

    # Networks that report views sort first: one we cannot measure is not one
    # that performed badly, and ranking it as zero would say exactly that.
    ranked = sorted(
        totals.items(),
        key=lambda kv: (1 if kv[1]["views_known"] else 0, kv[1]["views"]),
        reverse=True,
    )
    if not ranked:
        empty(ax, "Ще немає зібраних метрик")
        footnote(ax, ["Метрики збираються щодня о 04:00."], source="mr.Carpet")
        return png(fig)

    total_views = sum(d["views"] for _, d in ranked if d["views_known"])
    peak = max((d["views"] for _, d in ranked if d["views_known"]), default=0) or 1
    headline(ax, fmt_int(total_views), "переглядів разом")

    silent = {k: v for k, v in silent_networks().items() if k not in totals}
    row_h = rows_band(len(ranked) + (1 if silent else 0))

    y = BAND_TOP
    for i, (platform, data) in enumerate(ranked):
        centre = y - row_h / 2
        known = data["views_known"]
        row_label(
            ax,
            centre + row_h * 0.22,
            labels.get(platform, platform),
            fmt_int(data["views"]) if known else "н/д",
            right_muted=not known,
        )
        track(ax, centre - row_h * 0.10)
        if known and data["views"] > 0:
            bar(ax, centre - row_h * 0.10, data["views"] / peak, rank=i)

        detail = f"{fmt_int(data['likes'])} вподобань · {fmt_int(data['comments'])} коментарів"
        if data["videos"]:
            detail += f" · {data['videos']} відео"
        sub_label(ax, centre - row_h * 0.30, detail)
        y -= row_h

    # Named, not omitted: a missing row reads as a broken collector, a row
    # that explains itself reads as a known limit.
    for platform, reason in silent.items():
        ax.text(
            LEFT, y - row_h * 0.35,
            f"{labels.get(platform, platform)} — {reason}",
            transform=ax.transAxes, fontsize=8.5, color=MUTED, va="center",
        )
        y -= row_h * 0.22

    footnote(
        ax,
        [
            "Перегляд — хтось побачив відео у стрічці. Це не захід на сайт: "
            "GA4 бачить лише тих, хто перейшов далі.",
            "Скільки людей прийшло з кожної мережі — слайд «Звідки приходять», "
            "кампанія daily-video.",
        ],
        source="mr.Carpet",
    )
    return png(fig)


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
