"""Render GA4 dashboard PNGs for Telegram (matplotlib Agg)."""

from __future__ import annotations

import io
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Polygon, Rectangle  # noqa: E402

# Brand: ink + sand + forest (readable on phone screenshots)
BG = "#F3EFE8"
CARD = "#FFFcf7"
INK = "#171614"
MUTED = "#6A6760"
ACCENT = "#1B5F4F"
ACCENT_SOFT = "#D8E8E2"
GOLD = "#B8954A"
GRID = "#E6E0D4"
ZERO = "#D0CBC0"
DANGER = "#A14A3A"

FUNNEL_STEPS = (
    ("view_item", "Перегляд товару"),
    ("add_to_cart", "Додали в кошик"),
    ("view_cart", "Відкрили кошик"),
    ("begin_checkout", "Оформлення"),
    ("add_shipping_info", "Доставка"),
    ("add_payment_info", "Спосіб оплати"),
    ("purchase", "Покупка"),
)

# Telegram album looks best closer to square / 4:5
W, H = 8.2, 9.0


def _fig_bytes(fig) -> bytes:
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


def _fmt_int(raw: Any) -> str:
    try:
        f = float(raw or 0)
        return f"{int(round(f)):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "0"


def _fmt_money(raw: Any) -> str:
    try:
        f = float(raw or 0)
        if abs(f - int(f)) < 1e-9:
            return f"{int(f):,}".replace(",", " ")
        return f"{f:,.0f}".replace(",", " ")
    except (TypeError, ValueError):
        return "0"


def _human_source(source: str, medium: str) -> str:
    s = (source or "").strip() or "(not set)"
    m = (medium or "").strip() or "(not set)"
    if s in ("(not set)", "not set", "(none)") and m in (
        "(not set)",
        "not set",
        "(none)",
        "(not set)",
    ):
        return "Прямі / невідомі"
    if s in ("(direct)", "direct") or m == "(none)":
        return "Прямий захід"
    if m == "organic":
        return f"{s} · органіка"
    if m in ("cpc", "ppc", "paid"):
        return f"{s} · реклама"
    if m in ("social", "social-network"):
        return f"{s} · соцмережі"
    if m == "referral":
        return f"{s} · реферал"
    if s == "(not set)":
        s = "невідомо"
    if m == "(not set)":
        m = "невідомо"
    return f"{s} · {m}"


def _friendly_path(path: str) -> str:
    p = (path or "/").strip() or "/"
    if p in ("/", ""):
        return "Головна"
    if p.startswith("/catalog/collection"):
        return "Каталог колекцій"
    if p.startswith("/catalog/product/"):
        slug = p.rstrip("/").split("/")[-1]
        short = slug[:34] + ("…" if len(slug) > 34 else "")
        return f"Товар · {short}"
    if p.startswith("/checkout"):
        return "Оформлення замовлення"
    if p.startswith("/cart"):
        return "Кошик"
    if p.startswith("/favorite"):
        return "Обране"
    if len(p) > 42:
        return p[:39] + "…"
    return p


def _header(ax, title: str, subtitle: str):
    ax.text(
        0.04,
        0.965,
        title,
        transform=ax.transAxes,
        fontsize=16,
        fontweight="700",
        color=INK,
        va="top",
    )
    ax.text(
        0.04,
        0.915,
        subtitle,
        transform=ax.transAxes,
        fontsize=10,
        color=MUTED,
        va="top",
    )
    ax.plot(
        [0.04, 0.96],
        [0.88, 0.88],
        transform=ax.transAxes,
        color=GRID,
        linewidth=1.2,
        solid_capstyle="round",
    )


def _footer(fig, text: str = "mr.Carpet · Google Analytics 4"):
    fig.text(0.04, 0.015, text, color=MUTED, fontsize=8)


def render_funnel_chart(funnel: list[dict[str, Any]], *, days: int) -> bytes:
    by_event = {r.get("event"): int(r.get("events") or 0) for r in (funnel or [])}
    labels = [lab for _, lab in FUNNEL_STEPS]
    values = [by_event.get(key, 0) for key, _ in FUNNEL_STEPS]
    max_v = max(values) if values else 0
    base = max(max_v, 1)

    fig, ax = plt.subplots(figsize=(W, H))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    _header(ax, "4 · Воронка продажів", f"Останні {days} дн. · кількість подій GA4")

    # Classic funnel bands (top → bottom)
    n = len(labels)
    top_y, bottom_y = 0.84, 0.10
    band_h = (top_y - bottom_y) / n
    max_half = 0.40
    min_half = 0.10

    for i, (label, val) in enumerate(zip(labels, values)):
        y1 = top_y - i * band_h
        y0 = y1 - band_h * 0.82
        # width from absolute count (not relative to previous — GA events can skip steps)
        half = min_half + (max_half - min_half) * (val / base)
        cx = 0.52
        color = ACCENT if val > 0 else ZERO
        poly = Polygon(
            [
                (cx - half, y1),
                (cx + half, y1),
                (cx + half * 0.92, y0),
                (cx - half * 0.92, y0),
            ],
            closed=True,
            facecolor=color,
            edgecolor="white",
            linewidth=1.5,
            alpha=0.95 if val else 0.55,
        )
        ax.add_patch(poly)

        # left label
        ax.text(
            0.04,
            (y0 + y1) / 2,
            f"{i + 1}. {label}",
            va="center",
            ha="left",
            fontsize=10,
            color=INK if val else MUTED,
            fontweight="600" if val else "400",
        )
        # value inside / right
        ax.text(
            cx,
            (y0 + y1) / 2,
            _fmt_int(val) if val else "—",
            va="center",
            ha="center",
            fontsize=12,
            color="#FFFFFF" if val else MUTED,
            fontweight="700",
        )

        # conversion vs previous non-empty or previous step
        if i > 0:
            prev = values[i - 1]
            if prev > 0:
                rate = 100.0 * val / prev
                tip = f"{rate:.0f}% від попереднього"
            else:
                tip = "немає попередніх подій"
            ax.text(
                0.96,
                (y0 + y1) / 2,
                tip,
                va="center",
                ha="right",
                fontsize=8,
                color=MUTED,
            )

    if max_v == 0:
        ax.text(
            0.5,
            0.48,
            "За період ще немає ecommerce-подій",
            ha="center",
            va="center",
            fontsize=12,
            color=MUTED,
        )

    note = (
        "Ширина = кількість подій. Кроки можуть «стрибати», "
        "якщо частина подій не зібралась у браузері."
    )
    ax.text(0.04, 0.055, note, fontsize=8, color=MUTED, wrap=True)
    _footer(fig)
    return _fig_bytes(fig)


def render_sources_chart(sources: list[dict[str, Any]], *, days: int) -> bytes:
    rows = []
    for r in sources or []:
        sess = int(r.get("sessions") or 0)
        if sess <= 0:
            continue
        rows.append(
            {
                "label": _human_source(str(r.get("source") or ""), str(r.get("medium") or "")),
                "sessions": sess,
                "purchases": int(r.get("purchases") or 0),
            }
        )
    rows = rows[:7]
    total = sum(r["sessions"] for r in rows) or 1

    fig, ax = plt.subplots(figsize=(W, H))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    _header(ax, "5 · Звідки приходять", f"Останні {days} дн. · сесії за джерелом")

    if not rows:
        ax.text(
            0.5,
            0.5,
            "Немає даних про джерела за період",
            ha="center",
            color=MUTED,
            fontsize=12,
        )
        _footer(fig)
        return _fig_bytes(fig)

    # Donut
    sizes = [r["sessions"] for r in rows]
    palette = [
        "#1B5F4F",
        "#2F7A68",
        "#4A9482",
        "#6BAE9C",
        "#8FC4B4",
        "#B5D9CE",
        "#D5EBE4",
    ][: len(rows)]

    donut_ax = fig.add_axes([0.12, 0.42, 0.36, 0.36])
    donut_ax.set_facecolor(BG)
    donut_ax.pie(
        sizes,
        colors=palette,
        startangle=90,
        wedgeprops={"width": 0.42, "edgecolor": BG, "linewidth": 3},
    )
    donut_ax.text(
        0,
        0.06,
        _fmt_int(total),
        ha="center",
        va="center",
        fontsize=18,
        fontweight="700",
        color=INK,
    )
    donut_ax.text(0, -0.12, "сесій", ha="center", va="center", fontsize=10, color=MUTED)

    # Ranked list
    y0 = 0.78
    for i, r in enumerate(rows):
        y = y0 - i * 0.085
        pct = 100.0 * r["sessions"] / total
        # color chip
        chip = FancyBboxPatch(
            (0.52, y - 0.018),
            0.028,
            0.036,
            boxstyle="round,pad=0.004,rounding_size=0.008",
            transform=ax.transAxes,
            facecolor=palette[i],
            edgecolor="none",
            clip_on=False,
        )
        ax.add_patch(chip)
        ax.text(
            0.565,
            y,
            r["label"][:34],
            transform=ax.transAxes,
            va="center",
            fontsize=11,
            color=INK,
            fontweight="600",
        )
        # bar
        bar_w = 0.34 * (r["sessions"] / max(sizes))
        ax.add_patch(
            FancyBboxPatch(
                (0.565, y - 0.032),
                0.34,
                0.014,
                boxstyle="round,pad=0.002,rounding_size=0.004",
                transform=ax.transAxes,
                facecolor=GRID,
                edgecolor="none",
                clip_on=False,
            )
        )
        ax.add_patch(
            FancyBboxPatch(
                (0.565, y - 0.032),
                max(bar_w, 0.02),
                0.014,
                boxstyle="round,pad=0.002,rounding_size=0.004",
                transform=ax.transAxes,
                facecolor=palette[i],
                edgecolor="none",
                clip_on=False,
            )
        )
        right = f"{_fmt_int(r['sessions'])} · {pct:.0f}%"
        if r["purchases"]:
            right += f" · {_fmt_int(r['purchases'])} пок."
        ax.text(
            0.96,
            y,
            right,
            transform=ax.transAxes,
            va="center",
            ha="right",
            fontsize=10,
            color=MUTED,
        )

    ax.text(
        0.04,
        0.12,
        "«Прямі / невідомі» = GA4 не побачив utm/referrer "
        "(часто інкогніто, закладка або перехід без міток).",
        fontsize=8,
        color=MUTED,
        wrap=True,
    )
    _footer(fig)
    return _fig_bytes(fig)


def render_kpi_table(
    kpis: dict[str, str],
    revenue: dict[str, str],
    *,
    days: int,
    top_pages: list[dict[str, Any]] | None = None,
) -> bytes:
    """Traffic summary cards (revenue moved to dedicated slide)."""
    del top_pages  # kept for call-site compat
    fig, ax = plt.subplots(figsize=(W, H))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    _header(ax, "1 · Підсумок трафіку", f"Останні {days} дн. · хто заходив на сайт")

    users = _fmt_int(kpis.get("activeUsers", "0"))
    sessions = _fmt_int(kpis.get("sessions", "0"))
    views = _fmt_int(kpis.get("pageViews", "0"))
    engaged = _fmt_int(kpis.get("engagedSessions", "0"))
    try:
        sess_n = float(kpis.get("sessions") or 0) or 0
        eng_n = float(kpis.get("engagedSessions") or 0) or 0
        views_n = float(kpis.get("pageViews") or 0) or 0
        eng_pct = f"{(100 * eng_n / sess_n):.0f}%" if sess_n else "—"
        pages_per = f"{(views_n / sess_n):.1f}" if sess_n else "—"
    except (TypeError, ValueError):
        eng_pct = "—"
        pages_per = "—"

    cards = [
        (users, "Користувачі", "унікальні відвідувачі"),
        (sessions, "Сесії", "візити на сайт"),
        (views, "Перегляди", "сторінок відкрито"),
        (eng_pct, "Залученість", f"{engaged} залучених сесій"),
        (pages_per, "Сторінок / сесія", "глибина перегляду"),
        (
            _fmt_int(revenue.get("ecommercePurchases", "0")),
            "Покупки (коротко)",
            "деталі — на слайді «Продажі»",
        ),
    ]

    gap_x, gap_y = 0.035, 0.035
    card_w, card_h = 0.445, 0.18
    start_x, start_y = 0.04, 0.72
    for i, (value, title, hint) in enumerate(cards):
        col, row = i % 2, i // 2
        x = start_x + col * (card_w + gap_x)
        y = start_y - row * (card_h + gap_y)
        ax.add_patch(
            FancyBboxPatch(
                (x, y),
                card_w,
                card_h,
                boxstyle="round,pad=0.012,rounding_size=0.022",
                transform=ax.transAxes,
                facecolor=CARD,
                edgecolor=GRID,
                linewidth=1.2,
                clip_on=False,
            )
        )
        ax.add_patch(
            Rectangle(
                (x, y),
                0.014,
                card_h,
                transform=ax.transAxes,
                facecolor=ACCENT,
                edgecolor="none",
                clip_on=False,
            )
        )
        ax.text(
            x + 0.045,
            y + card_h * 0.62,
            value,
            transform=ax.transAxes,
            fontsize=22,
            fontweight="700",
            color=INK,
            va="center",
        )
        ax.text(
            x + 0.045,
            y + card_h * 0.34,
            title,
            transform=ax.transAxes,
            fontsize=12,
            color=INK,
            fontweight="600",
            va="center",
        )
        ax.text(
            x + 0.045,
            y + card_h * 0.16,
            hint,
            transform=ax.transAxes,
            fontsize=9,
            color=MUTED,
            va="center",
        )

    ax.text(
        0.04,
        0.08,
        "Далі в альбомі: динаміка по днях → залученість → воронка → "
        "джерела → сторінки → продажі.",
        transform=ax.transAxes,
        fontsize=9,
        color=MUTED,
    )
    _footer(fig)
    return _fig_bytes(fig)


def render_daily_trend_chart(daily: list[dict[str, Any]], *, days: int) -> bytes:
    rows = list(daily or [])
    fig, ax = plt.subplots(figsize=(W, H))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    _header_axes = fig.add_axes([0, 0, 1, 1])
    _header_axes.set_xlim(0, 1)
    _header_axes.set_ylim(0, 1)
    _header_axes.axis("off")
    _header_axes.set_zorder(0)
    _header(_header_axes, "2 · Динаміка по днях", f"Останні {days} дн. · користувачі та сесії")

    plot_ax = fig.add_axes([0.12, 0.14, 0.78, 0.62])
    plot_ax.set_facecolor(CARD)
    for spine in plot_ax.spines.values():
        spine.set_color(GRID)
    plot_ax.tick_params(colors=MUTED, labelsize=8)
    plot_ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    plot_ax.set_axisbelow(True)

    if not rows:
        plot_ax.text(0.5, 0.5, "Немає денних даних", ha="center", transform=plot_ax.transAxes, color=MUTED)
    else:
        x = list(range(len(rows)))
        users = [r.get("users") or 0 for r in rows]
        sessions = [r.get("sessions") or 0 for r in rows]
        labels = [r.get("label") or "" for r in rows]
        plot_ax.fill_between(x, users, color=ACCENT_SOFT, alpha=0.9)
        plot_ax.plot(x, users, color=ACCENT, linewidth=2.4, marker="o", markersize=4, label="Користувачі")
        plot_ax.plot(
            x,
            sessions,
            color=GOLD,
            linewidth=2.0,
            marker="s",
            markersize=3.5,
            label="Сесії",
        )
        step = max(1, len(labels) // 7)
        plot_ax.set_xticks(x[::step])
        plot_ax.set_xticklabels(labels[::step], rotation=0)
        plot_ax.legend(frameon=False, fontsize=9, loc="upper left")
        plot_ax.set_ylabel("Кількість", color=MUTED, fontsize=9)

    _footer(fig)
    return _fig_bytes(fig)


def render_engagement_chart(kpis: dict[str, str], *, days: int) -> bytes:
    fig, ax = plt.subplots(figsize=(W, H))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    _header(ax, "3 · Залученість", f"Останні {days} дн. · якість візитів")

    try:
        sessions = float(kpis.get("sessions") or 0)
        engaged = float(kpis.get("engagedSessions") or 0)
        users = float(kpis.get("activeUsers") or 0)
        views = float(kpis.get("pageViews") or 0)
    except (TypeError, ValueError):
        sessions = engaged = users = views = 0

    other = max(sessions - engaged, 0)
    if sessions <= 0:
        ax.text(0.5, 0.5, "Немає сесій за період", ha="center", color=MUTED, fontsize=12)
        _footer(fig)
        return _fig_bytes(fig)

    donut = fig.add_axes([0.18, 0.38, 0.64, 0.42])
    donut.set_facecolor(BG)
    donut.pie(
        [engaged or 0.001, other or 0.001],
        colors=[ACCENT, ZERO],
        startangle=90,
        wedgeprops={"width": 0.45, "edgecolor": BG, "linewidth": 4},
    )
    pct = 100.0 * engaged / sessions if sessions else 0
    donut.text(0, 0.08, f"{pct:.0f}%", ha="center", va="center", fontsize=28, fontweight="700", color=INK)
    donut.text(0, -0.12, "залучених\nсесій", ha="center", va="center", fontsize=11, color=MUTED)

    metrics = [
        (f"{_fmt_int(engaged)} / {_fmt_int(sessions)}", "Залучені / усі сесії"),
        (
            f"{(views / sessions):.1f}" if sessions else "—",
            "Переглядів на сесію",
        ),
        (
            f"{(sessions / users):.1f}" if users else "—",
            "Сесій на користувача",
        ),
    ]
    for i, (val, lab) in enumerate(metrics):
        x = 0.06 + i * 0.31
        ax.add_patch(
            FancyBboxPatch(
                (x, 0.12),
                0.28,
                0.16,
                boxstyle="round,pad=0.01,rounding_size=0.02",
                transform=ax.transAxes,
                facecolor=CARD,
                edgecolor=GRID,
                clip_on=False,
            )
        )
        ax.text(x + 0.14, 0.22, val, transform=ax.transAxes, ha="center", fontsize=14, fontweight="700", color=INK)
        ax.text(x + 0.14, 0.155, lab, transform=ax.transAxes, ha="center", fontsize=8, color=MUTED)

    _footer(fig)
    return _fig_bytes(fig)


def render_top_pages_chart(top_pages: list[dict[str, Any]], *, days: int) -> bytes:
    pages = [p for p in (top_pages or []) if int(float(p.get("views") or 0)) > 0][:8]
    fig, ax = plt.subplots(figsize=(W, H))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    _header(ax, "6 · Популярні сторінки", f"Останні {days} дн. · за переглядами")

    if not pages:
        ax.text(0.5, 0.5, "Немає переглядів сторінок", ha="center", color=MUTED, fontsize=12)
        _footer(fig)
        return _fig_bytes(fig)

    max_v = max(int(float(p.get("views") or 0)) for p in pages) or 1
    for i, p in enumerate(pages):
        y = 0.80 - i * 0.085
        views_n = int(float(p.get("views") or 0))
        users_n = int(float(p.get("users") or 0))
        label = _friendly_path(str(p.get("path") or "/"))
        ax.text(0.05, y + 0.028, f"{i + 1}. {label}", transform=ax.transAxes, fontsize=11, color=INK, fontweight="600")
        ax.text(
            0.95,
            y + 0.028,
            f"{_fmt_int(views_n)} перегл. · {_fmt_int(users_n)} корист.",
            transform=ax.transAxes,
            fontsize=9,
            color=MUTED,
            ha="right",
        )
        ax.add_patch(
            FancyBboxPatch(
                (0.05, y - 0.01),
                0.90,
                0.018,
                boxstyle="round,pad=0.001,rounding_size=0.005",
                transform=ax.transAxes,
                facecolor=GRID,
                edgecolor="none",
                clip_on=False,
            )
        )
        ax.add_patch(
            FancyBboxPatch(
                (0.05, y - 0.01),
                0.90 * (views_n / max_v),
                0.018,
                boxstyle="round,pad=0.001,rounding_size=0.005",
                transform=ax.transAxes,
                facecolor=ACCENT,
                edgecolor="none",
                clip_on=False,
            )
        )
    _footer(fig)
    return _fig_bytes(fig)


def render_revenue_chart(
    revenue: dict[str, str],
    funnel: list[dict[str, Any]],
    *,
    days: int,
) -> bytes:
    fig, ax = plt.subplots(figsize=(W, H))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    _header(ax, "7 · Продажі", f"Останні {days} дн. · ecommerce з GA4")

    purchases = _fmt_int(revenue.get("ecommercePurchases", "0"))
    rev = _fmt_money(revenue.get("purchaseRevenue", "0"))
    avg = _fmt_money(revenue.get("averagePurchaseRevenue", "0"))
    by_event = {r.get("event"): int(r.get("events") or 0) for r in (funnel or [])}
    view_n = by_event.get("view_item", 0)
    cart_n = by_event.get("add_to_cart", 0)
    purch_evt = by_event.get("purchase", 0)
    cvr = f"{(100.0 * purch_evt / view_n):.1f}%" if view_n else "—"

    big = [
        (rev, "Виручка, грн", GOLD),
        (purchases, "Покупки", ACCENT),
        (avg, "Середній чек", ACCENT),
        (cvr, "Конверсія view→purchase", ACCENT),
    ]
    for i, (val, lab, color) in enumerate(big):
        y = 0.72 - i * 0.14
        ax.add_patch(
            FancyBboxPatch(
                (0.06, y),
                0.88,
                0.12,
                boxstyle="round,pad=0.012,rounding_size=0.02",
                transform=ax.transAxes,
                facecolor=CARD,
                edgecolor=color if i == 0 else GRID,
                linewidth=1.8 if i == 0 else 1.1,
                clip_on=False,
            )
        )
        ax.text(0.1, y + 0.07, val, transform=ax.transAxes, fontsize=22, fontweight="700", color=INK, va="center")
        ax.text(0.1, y + 0.03, lab, transform=ax.transAxes, fontsize=11, color=MUTED, va="center")

    ax.text(
        0.06,
        0.10,
        f"Події: перегляд {view_n} · у кошик {cart_n} · purchase {purch_evt}",
        transform=ax.transAxes,
        fontsize=9,
        color=MUTED,
    )
    _footer(fig)
    return _fig_bytes(fig)


def render_realtime_chart(data: dict[str, Any]) -> bytes:
    screens = [s for s in (data.get("screens") or []) if int(s.get("users") or 0) > 0][:8]
    total = int(data.get("active_users") or sum(int(s.get("users") or 0) for s in screens))

    fig, ax = plt.subplots(figsize=(W, H * 0.85))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    _header(ax, "Зараз на сайті", f"Realtime · приблизно останні 30 хв · {total} онлайн")

    if not screens:
        ax.text(0.5, 0.5, "Нікого в realtime зараз", ha="center", color=MUTED, fontsize=13)
        _footer(fig)
        return _fig_bytes(fig)

    max_u = max(int(s.get("users") or 0) for s in screens) or 1
    for i, s in enumerate(screens):
        y = 0.78 - i * 0.08
        users = int(s.get("users") or 0)
        title = _friendly_path(str(s.get("screen") or ""))
        if len(title) > 40 and not title.startswith("Товар"):
            # realtime often gives page titles — keep short
            title = (str(s.get("screen") or ""))[:40]
        ax.text(0.04, y + 0.02, title, transform=ax.transAxes, fontsize=10, color=INK, va="center")
        ax.text(
            0.96,
            y + 0.02,
            _fmt_int(users),
            transform=ax.transAxes,
            fontsize=11,
            color=ACCENT,
            ha="right",
            va="center",
            fontweight="700",
        )
        ax.add_patch(
            FancyBboxPatch(
                (0.04, y - 0.02),
                0.92,
                0.014,
                boxstyle="round,pad=0.001,rounding_size=0.004",
                transform=ax.transAxes,
                facecolor=GRID,
                edgecolor="none",
                clip_on=False,
            )
        )
        ax.add_patch(
            FancyBboxPatch(
                (0.04, y - 0.02),
                0.92 * (users / max_u),
                0.014,
                boxstyle="round,pad=0.001,rounding_size=0.004",
                transform=ax.transAxes,
                facecolor=ACCENT,
                edgecolor="none",
                clip_on=False,
            )
        )
    _footer(fig)
    return _fig_bytes(fig)


def build_dashboard_photos(dashboard: dict[str, Any]) -> list[tuple[str, bytes]]:
    """Up to 7 slides (Telegram album max 10)."""
    days = int(dashboard.get("days") or 7)
    kpis = dashboard.get("kpis") or {}
    revenue = dashboard.get("revenue") or {}
    funnel = dashboard.get("funnel") or []
    return [
        (
            "01_traffic.png",
            render_kpi_table(kpis, revenue, days=days),
        ),
        (
            "02_daily.png",
            render_daily_trend_chart(dashboard.get("daily") or [], days=days),
        ),
        (
            "03_engagement.png",
            render_engagement_chart(kpis, days=days),
        ),
        (
            "04_funnel.png",
            render_funnel_chart(funnel, days=days),
        ),
        (
            "05_sources.png",
            render_sources_chart(dashboard.get("sources") or [], days=days),
        ),
        (
            "06_pages.png",
            render_top_pages_chart(dashboard.get("top_pages") or [], days=days),
        ),
        (
            "07_sales.png",
            render_revenue_chart(revenue, funnel, days=days),
        ),
    ]


def build_caption(dashboard: dict[str, Any]) -> str:
    days = int(dashboard.get("days") or 7)
    k = dashboard.get("kpis") or {}
    r = dashboard.get("revenue") or {}
    funnel = dashboard.get("funnel") or []
    purch = next((x for x in funnel if x.get("event") == "purchase"), None)
    purch_events = purch.get("events") if purch else 0

    return "\n".join(
        [
            f"GA4 · останні {days} дн. · 7 слайдів",
            f"👥 {_fmt_int(k.get('activeUsers'))} корист. · "
            f"{_fmt_int(k.get('sessions'))} сесій · "
            f"{_fmt_int(k.get('pageViews'))} перегл.",
            f"🛒 Покупки: {_fmt_int(r.get('ecommercePurchases'))} · "
            f"виручка {_fmt_money(r.get('purchaseRevenue'))} грн · "
            f"purchase: {_fmt_int(purch_events)}",
            "1 трафік · 2 дні · 3 залученість · 4 воронка · 5 джерела · 6 сторінки · 7 продажі",
        ]
    )


def build_realtime_caption(data: dict[str, Any]) -> str:
    total = int(data.get("active_users") or 0)
    return f"Realtime GA4 (~30 хв)\nЗараз онлайн: {total}"
