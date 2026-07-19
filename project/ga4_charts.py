"""Render GA4 dashboard PNGs (matplotlib Agg, no GUI)."""

from __future__ import annotations

import io
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

# mr.Carpet — ink + warm sand (not purple / not terracotta-cream AI cliché)
BG = "#F6F3EE"
INK = "#1A1A18"
MUTED = "#5C5A55"
ACCENT = "#1F5C4C"
ACCENT_2 = "#C4A35A"
GRID = "#E4DFD6"
BAR = "#2A7A66"

FUNNEL_LABELS = {
    "view_item": "Перегляд",
    "add_to_cart": "У кошик",
    "view_cart": "Кошик",
    "begin_checkout": "Checkout",
    "add_shipping_info": "Доставка",
    "add_payment_info": "Оплата",
    "purchase": "Покупка",
}


def _fig_bytes(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(
        buf,
        format="png",
        dpi=160,
        facecolor=fig.get_facecolor(),
        bbox_inches="tight",
        pad_inches=0.25,
    )
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _style_axes(ax):
    ax.set_facecolor(BG)
    ax.tick_params(colors=MUTED, labelsize=9)
    for spine in ax.spines.values():
        spine.set_color(GRID)
    ax.yaxis.label.set_color(MUTED)
    ax.xaxis.label.set_color(MUTED)
    ax.title.set_color(INK)


def render_funnel_chart(funnel: list[dict[str, Any]], *, days: int) -> bytes:
    labels = [FUNNEL_LABELS.get(r["event"], r["event"]) for r in funnel]
    values = [int(r.get("events") or 0) for r in funnel]

    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    fig.patch.set_facecolor(BG)
    _style_axes(ax)

    y = list(range(len(labels)))[::-1]
    bars = ax.barh(y, values, color=BAR, height=0.62, edgecolor="none")
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=10, color=INK)
    ax.set_xlabel("Події", fontsize=10)
    ax.set_title(f"Ecommerce-воронка · останні {days} дн.", fontsize=14, pad=12, fontweight="600")
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)

    max_v = max(values) if values else 0
    for bar, val in zip(bars, values):
        ax.text(
            bar.get_width() + max(max_v * 0.01, 0.3),
            bar.get_y() + bar.get_height() / 2,
            f"{val:,}".replace(",", " "),
            va="center",
            ha="left",
            color=INK,
            fontsize=9,
        )
    if max_v == 0:
        ax.text(0.5, 0.5, "Немає подій за період", transform=ax.transAxes, ha="center", color=MUTED)

    ax.set_xlim(0, max(max_v * 1.18, 1))
    fig.text(0.01, 0.01, "mr.Carpet · GA4", color=MUTED, fontsize=8)
    return _fig_bytes(fig)


def render_sources_chart(sources: list[dict[str, Any]], *, days: int) -> bytes:
    rows = (sources or [])[:8]
    labels = [f"{r['source']} / {r['medium']}" for r in rows] or ["(немає даних)"]
    values = [int(r.get("sessions") or 0) for r in rows] or [0]

    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    fig.patch.set_facecolor(BG)
    _style_axes(ax)

    y = list(range(len(labels)))[::-1]
    bars = ax.barh(y, values, color=ACCENT, height=0.62, edgecolor="none")
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9, color=INK)
    ax.set_xlabel("Сесії", fontsize=10)
    ax.set_title(f"Джерела трафіку · останні {days} дн.", fontsize=14, pad=12, fontweight="600")
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)

    max_v = max(values) if values else 0
    for bar, val, row in zip(bars, values, rows or [{}]):
        purch = int(row.get("purchases") or 0)
        suffix = f"  ·  {purch} покуп." if purch else ""
        ax.text(
            bar.get_width() + max(max_v * 0.01, 0.3),
            bar.get_y() + bar.get_height() / 2,
            f"{val:,}{suffix}".replace(",", " "),
            va="center",
            ha="left",
            color=INK,
            fontsize=9,
        )
    ax.set_xlim(0, max(max_v * 1.25, 1))
    fig.text(0.01, 0.01, "mr.Carpet · GA4", color=MUTED, fontsize=8)
    return _fig_bytes(fig)


def render_kpi_table(
    kpis: dict[str, str],
    revenue: dict[str, str],
    *,
    days: int,
    top_pages: list[dict[str, Any]] | None = None,
) -> bytes:
    fig, ax = plt.subplots(figsize=(9.5, 5.6))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.axis("off")
    ax.set_title(f"KPI · останні {days} дн.", fontsize=14, pad=10, color=INK, fontweight="600")

    def fmt_num(raw: str) -> str:
        try:
            f = float(raw or 0)
            if abs(f - int(f)) < 1e-9:
                return f"{int(f):,}".replace(",", " ")
            return f"{f:,.2f}".replace(",", " ")
        except (TypeError, ValueError):
            return str(raw or "0")

    cells = [
        ("Користувачі", fmt_num(kpis.get("activeUsers", "0"))),
        ("Сесії", fmt_num(kpis.get("sessions", "0"))),
        ("Перегляди", fmt_num(kpis.get("pageViews", "0"))),
        ("Engaged сесії", fmt_num(kpis.get("engagedSessions", "0"))),
        ("Покупки", fmt_num(revenue.get("ecommercePurchases", "0"))),
        ("Revenue (UAH)", fmt_num(revenue.get("purchaseRevenue", "0"))),
        ("Avg purchase", fmt_num(revenue.get("averagePurchaseRevenue", "0"))),
    ]

    # KPI cards
    cols = 4
    card_w, card_h = 0.22, 0.18
    start_x, start_y = 0.06, 0.68
    for i, (label, value) in enumerate(cells[:4]):
        col, row = i % cols, i // cols
        x = start_x + col * (card_w + 0.02)
        y = start_y - row * (card_h + 0.04)
        box = FancyBboxPatch(
            (x, y),
            card_w,
            card_h,
            boxstyle="round,pad=0.012,rounding_size=0.02",
            transform=ax.transAxes,
            facecolor="#FFFFFF",
            edgecolor=GRID,
            linewidth=1.2,
            clip_on=False,
        )
        ax.add_patch(box)
        ax.text(
            x + card_w / 2,
            y + card_h * 0.62,
            value,
            transform=ax.transAxes,
            ha="center",
            va="center",
            fontsize=16,
            color=INK,
            fontweight="700",
        )
        ax.text(
            x + card_w / 2,
            y + card_h * 0.28,
            label,
            transform=ax.transAxes,
            ha="center",
            va="center",
            fontsize=9,
            color=MUTED,
        )

    # Revenue row
    for i, (label, value) in enumerate(cells[4:]):
        x = start_x + i * (card_w + 0.02)
        y = 0.42
        box = FancyBboxPatch(
            (x, y),
            card_w,
            card_h,
            boxstyle="round,pad=0.012,rounding_size=0.02",
            transform=ax.transAxes,
            facecolor="#FFFFFF",
            edgecolor=ACCENT_2,
            linewidth=1.4,
            clip_on=False,
        )
        ax.add_patch(box)
        ax.text(
            x + card_w / 2,
            y + card_h * 0.62,
            value,
            transform=ax.transAxes,
            ha="center",
            va="center",
            fontsize=15,
            color=INK,
            fontweight="700",
        )
        ax.text(
            x + card_w / 2,
            y + card_h * 0.28,
            label,
            transform=ax.transAxes,
            ha="center",
            va="center",
            fontsize=9,
            color=MUTED,
        )

    # Top pages
    pages = (top_pages or [])[:5]
    ax.text(0.06, 0.34, "Топ сторінки", transform=ax.transAxes, fontsize=11, color=INK, fontweight="600")
    if pages:
        lines = []
        for p in pages:
            path = (p.get("path") or "")[:48]
            lines.append(f"{fmt_num(str(p.get('views', '0')))} перегл.  ·  {path}")
        ax.text(
            0.06,
            0.30,
            "\n".join(lines),
            transform=ax.transAxes,
            fontsize=9,
            color=MUTED,
            va="top",
            linespacing=1.55,
            family="DejaVu Sans",
        )
    else:
        ax.text(0.06, 0.28, "Немає даних", transform=ax.transAxes, fontsize=9, color=MUTED)

    fig.text(0.01, 0.01, "mr.Carpet · GA4 · дані з ресурсу, не оцінка моделі", color=MUTED, fontsize=8)
    return _fig_bytes(fig)


def render_realtime_chart(data: dict[str, Any]) -> bytes:
    screens = (data.get("screens") or [])[:8]
    labels = [(s.get("screen") or "")[:40] for s in screens] or ["(нікого)"]
    values = [int(s.get("users") or 0) for s in screens] or [0]
    total = int(data.get("active_users") or sum(values))

    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    fig.patch.set_facecolor(BG)
    _style_axes(ax)
    y = list(range(len(labels)))[::-1]
    ax.barh(y, values, color=ACCENT, height=0.62, edgecolor="none")
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9, color=INK)
    ax.set_xlabel("Active users", fontsize=10)
    ax.set_title(f"Realtime · ~30 хв · {total} users", fontsize=14, pad=12, fontweight="600")
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    fig.text(0.01, 0.01, "mr.Carpet · GA4", color=MUTED, fontsize=8)
    return _fig_bytes(fig)


def build_dashboard_photos(dashboard: dict[str, Any]) -> list[tuple[str, bytes]]:
    days = int(dashboard.get("days") or 7)
    photos = [
        (
            "funnel.png",
            render_funnel_chart(dashboard.get("funnel") or [], days=days),
        ),
        (
            "sources.png",
            render_sources_chart(dashboard.get("sources") or [], days=days),
        ),
        (
            "kpi.png",
            render_kpi_table(
                dashboard.get("kpis") or {},
                dashboard.get("revenue") or {},
                days=days,
                top_pages=dashboard.get("top_pages"),
            ),
        ),
    ]
    return photos


def build_caption(dashboard: dict[str, Any]) -> str:
    days = int(dashboard.get("days") or 7)
    k = dashboard.get("kpis") or {}
    r = dashboard.get("revenue") or {}
    funnel = dashboard.get("funnel") or []
    purchases_evt = next((x for x in funnel if x.get("event") == "purchase"), None)
    purch_events = purchases_evt.get("events") if purchases_evt else 0

    def n(key: str, src: dict) -> str:
        try:
            f = float(src.get(key) or 0)
            if abs(f - int(f)) < 1e-9:
                return f"{int(f):,}".replace(",", " ")
            return f"{f:,.0f}".replace(",", " ")
        except (TypeError, ValueError):
            return "0"

    lines = [
        f"📊 GA4 · останні {days} дн. (дані ресурсу, не оцінка)",
        f"Користувачі: {n('activeUsers', k)} · Сесії: {n('sessions', k)} · Перегляди: {n('pageViews', k)}",
        f"Покупки (ecommerce): {n('ecommercePurchases', r)} · Revenue: {n('purchaseRevenue', r)} UAH",
        f"Подія purchase: {purch_events}",
    ]
    return "\n".join(lines)


def build_realtime_caption(data: dict[str, Any]) -> str:
    total = int(data.get("active_users") or 0)
    return f"⚡️ Realtime GA4 (~30 хв)\nActive users: {total}"
