"""Render GA4 dashboard PNGs for Telegram (matplotlib Agg)."""

from __future__ import annotations

import io
import textwrap
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Polygon, Rectangle  # noqa: E402

BG = "#F3EFE8"
CARD = "#FFFcf7"
INK = "#171614"
MUTED = "#6A6760"
ACCENT = "#1B5F4F"
ACCENT_SOFT = "#D8E8E2"
GOLD = "#B8954A"
GRID = "#E6E0D4"
ZERO = "#D0CBC0"

FUNNEL_STEPS = (
    ("view_item", "Перегляд товару"),
    ("add_to_cart", "Додали в кошик"),
    ("view_cart", "Відкрили кошик"),
    ("begin_checkout", "Оформлення"),
    ("add_shipping_info", "Доставка"),
    ("add_payment_info", "Спосіб оплати"),
    ("purchase", "Покупка"),
)

# Tall phone-friendly frame; bottom ~22% reserved for glossary
W, H = 8.0, 10.0
HEADER_Y = 0.94
SUB_Y = 0.905
RULE_Y = 0.875
CONTENT_TOP = 0.85
GLOSS_TOP = 0.20
FOOT_Y = 0.018


def _fig_bytes(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(
        buf,
        format="png",
        dpi=180,
        facecolor=fig.get_facecolor(),
        bbox_inches="tight",
        pad_inches=0.12,
    )
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _blank_fig():
    fig, ax = plt.subplots(figsize=(W, H))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    return fig, ax


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
        short = slug[:28] + ("…" if len(slug) > 28 else "")
        return f"Товар · {short}"
    if p.startswith("/checkout"):
        return "Оформлення замовлення"
    if p.startswith("/cart"):
        return "Кошик"
    if p.startswith("/favorite"):
        return "Обране"
    if len(p) > 36:
        return p[:33] + "…"
    return p


def _header(ax, title: str, subtitle: str) -> None:
    ax.text(
        0.05,
        HEADER_Y,
        title,
        transform=ax.transAxes,
        fontsize=17,
        fontweight="700",
        color=INK,
        va="top",
    )
    ax.text(
        0.05,
        SUB_Y,
        subtitle,
        transform=ax.transAxes,
        fontsize=10,
        color=MUTED,
        va="top",
    )
    ax.plot(
        [0.05, 0.95],
        [RULE_Y, RULE_Y],
        transform=ax.transAxes,
        color=GRID,
        linewidth=1.2,
        solid_capstyle="round",
    )


def _glossary(ax, lines: list[str]) -> None:
    """Bottom help box — plain language for non-analysts."""
    ax.add_patch(
        FancyBboxPatch(
            (0.05, 0.04),
            0.90,
            GLOSS_TOP - 0.045,
            boxstyle="round,pad=0.012,rounding_size=0.018",
            transform=ax.transAxes,
            facecolor="#EFEAE2",
            edgecolor=GRID,
            linewidth=1.0,
            clip_on=False,
        )
    )
    ax.text(
        0.07,
        GLOSS_TOP - 0.01,
        "Простими словами",
        transform=ax.transAxes,
        fontsize=9,
        fontweight="700",
        color=ACCENT,
        va="top",
    )
    y = GLOSS_TOP - 0.035
    for line in lines:
        for wrapped in textwrap.wrap(line, width=62) or [""]:
            ax.text(
                0.07,
                y,
                wrapped,
                transform=ax.transAxes,
                fontsize=8.2,
                color=MUTED,
                va="top",
            )
            y -= 0.022
            if y < 0.05:
                break


def _footer(fig) -> None:
    fig.text(0.05, FOOT_Y, "mr.Carpet · Google Analytics 4", color=MUTED, fontsize=7.5)


def render_funnel_chart(funnel: list[dict[str, Any]], *, days: int) -> bytes:
    by_event = {r.get("event"): int(r.get("events") or 0) for r in (funnel or [])}
    labels = [lab for _, lab in FUNNEL_STEPS]
    values = [by_event.get(key, 0) for key, _ in FUNNEL_STEPS]
    max_v = max(values) if values else 0
    base = max(max_v, 1)

    fig, ax = _blank_fig()
    _header(ax, "4 · Воронка продажів", f"Останні {days} дн. · шлях від перегляду до покупки")

    n = len(labels)
    top_y, bottom_y = CONTENT_TOP - 0.02, GLOSS_TOP + 0.04
    band_h = (top_y - bottom_y) / n
    max_half, min_half = 0.28, 0.08
    cx = 0.55

    for i, (label, val) in enumerate(zip(labels, values)):
        y1 = top_y - i * band_h
        y0 = y1 - band_h * 0.78
        half = min_half + (max_half - min_half) * (val / base)
        color = ACCENT if val > 0 else ZERO
        ax.add_patch(
            Polygon(
                [
                    (cx - half, y1),
                    (cx + half, y1),
                    (cx + half * 0.9, y0),
                    (cx - half * 0.9, y0),
                ],
                closed=True,
                facecolor=color,
                edgecolor=BG,
                linewidth=2,
                alpha=0.95 if val else 0.5,
            )
        )
        ax.text(
            0.05,
            (y0 + y1) / 2,
            f"{i + 1}. {label}",
            va="center",
            ha="left",
            fontsize=9,
            color=INK if val else MUTED,
            fontweight="600" if val else "400",
        )
        ax.text(
            cx,
            (y0 + y1) / 2,
            _fmt_int(val) if val else "—",
            va="center",
            ha="center",
            fontsize=11,
            color="#FFFFFF" if val else MUTED,
            fontweight="700",
        )
        if i > 0:
            prev = values[i - 1]
            tip = f"{(100.0 * val / prev):.0f}%" if prev > 0 else "—"
            ax.text(
                0.92,
                (y0 + y1) / 2,
                tip,
                va="center",
                ha="right",
                fontsize=8,
                color=MUTED,
            )

    _glossary(
        ax,
        [
            "Кожен рядок — крок покупця. Цифра справа від смуги = % від попереднього кроку.",
            "Якщо крок «порожній», а далі є покупка — частина подій не записалась "
            "(блок реклами, швидке закриття сторінки).",
        ],
    )
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
    rows = rows[:6]
    total = sum(r["sessions"] for r in rows) or 1

    fig, ax = _blank_fig()
    _header(ax, "5 · Звідки приходять", f"Останні {days} дн. · звідки люди потрапляють на сайт")

    if not rows:
        ax.text(0.5, 0.55, "Немає даних про джерела", ha="center", color=MUTED, fontsize=12)
        _glossary(ax, ["Джерело — звідки прийшов відвідувач: Google, Instagram, пряме посилання тощо."])
        _footer(fig)
        return _fig_bytes(fig)

    sizes = [r["sessions"] for r in rows]
    palette = ["#1B5F4F", "#2F7A68", "#4A9482", "#6BAE9C", "#8FC4B4", "#B5D9CE"][: len(rows)]

    donut = fig.add_axes([0.10, 0.38, 0.38, 0.38])
    donut.set_facecolor(BG)
    donut.pie(
        sizes,
        colors=palette,
        startangle=90,
        wedgeprops={"width": 0.45, "edgecolor": BG, "linewidth": 3},
    )
    donut.text(0, 0.06, _fmt_int(total), ha="center", va="center", fontsize=20, fontweight="700", color=INK)
    donut.text(0, -0.14, "сесій", ha="center", va="center", fontsize=11, color=MUTED)

    # List below donut / right — stacked to avoid overlap
    y = CONTENT_TOP - 0.02
    for i, r in enumerate(rows):
        pct = 100.0 * r["sessions"] / total
        ax.add_patch(
            FancyBboxPatch(
                (0.52, y - 0.055),
                0.43,
                0.07,
                boxstyle="round,pad=0.008,rounding_size=0.012",
                transform=ax.transAxes,
                facecolor=CARD,
                edgecolor=GRID,
                clip_on=False,
            )
        )
        ax.add_patch(
            Rectangle(
                (0.535, y - 0.035),
                0.022,
                0.028,
                transform=ax.transAxes,
                facecolor=palette[i],
                edgecolor="none",
                clip_on=False,
            )
        )
        ax.text(
            0.57,
            y - 0.012,
            r["label"][:28],
            transform=ax.transAxes,
            fontsize=10,
            color=INK,
            fontweight="600",
            va="center",
        )
        detail = f"{_fmt_int(r['sessions'])} сесій · {pct:.0f}%"
        if r["purchases"]:
            detail += f" · {_fmt_int(r['purchases'])} пок."
        ax.text(
            0.57,
            y - 0.038,
            detail,
            transform=ax.transAxes,
            fontsize=8,
            color=MUTED,
            va="center",
        )
        y -= 0.09

    _glossary(
        ax,
        [
            "Сесія — один візит на сайт (поки людина дивиться сторінки).",
            "«Прямі / невідомі» — GA4 не бачив мітки реклами чи referrer "
            "(закладка, інкогніто, месенджер без utm).",
        ],
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
    del top_pages
    fig, ax = _blank_fig()
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
        (users, "Користувачі", "скільки різних людей"),
        (sessions, "Сесії", "скільки візитів"),
        (views, "Перегляди", "скільки сторінок відкрили"),
        (eng_pct, "Залученість", f"{engaged} «живих» візитів"),
        (pages_per, "Сторінок / сесія", "наскільки глибоко дивились"),
        (
            _fmt_int(revenue.get("ecommercePurchases", "0")),
            "Покупки",
            "деталі — слайд 7",
        ),
    ]

    gap_x, gap_y = 0.04, 0.028
    card_w, card_h = 0.43, 0.145
    start_x, start_y = 0.05, CONTENT_TOP - 0.155
    for i, (value, title, hint) in enumerate(cards):
        col, row = i % 2, i // 2
        x = start_x + col * (card_w + gap_x)
        y = start_y - row * (card_h + gap_y)
        ax.add_patch(
            FancyBboxPatch(
                (x, y),
                card_w,
                card_h,
                boxstyle="round,pad=0.01,rounding_size=0.02",
                transform=ax.transAxes,
                facecolor=CARD,
                edgecolor=GRID,
                linewidth=1.1,
                clip_on=False,
            )
        )
        ax.add_patch(
            Rectangle(
                (x, y),
                0.012,
                card_h,
                transform=ax.transAxes,
                facecolor=ACCENT,
                edgecolor="none",
                clip_on=False,
            )
        )
        ax.text(
            x + 0.04,
            y + card_h * 0.68,
            value,
            transform=ax.transAxes,
            fontsize=20,
            fontweight="700",
            color=INK,
            va="center",
        )
        ax.text(
            x + 0.04,
            y + card_h * 0.38,
            title,
            transform=ax.transAxes,
            fontsize=11,
            color=INK,
            fontweight="600",
            va="center",
        )
        ax.text(
            x + 0.04,
            y + card_h * 0.16,
            hint,
            transform=ax.transAxes,
            fontsize=8,
            color=MUTED,
            va="center",
        )

    _glossary(
        ax,
        [
            "Користувач — унікальна людина. Сесія — один візит (можна кілька за день).",
            "Залученість — % візитів, де людина реально взаємодіяла "
            "(не просто відкрила і одразу пішла).",
        ],
    )
    _footer(fig)
    return _fig_bytes(fig)


def render_daily_trend_chart(daily: list[dict[str, Any]], *, days: int) -> bytes:
    rows = list(daily or [])
    fig = plt.figure(figsize=(W, H), facecolor=BG)

    # Full-bleed canvas for header/glossary (no ticks)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(BG)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    _header(ax, "2 · Динаміка по днях", f"Останні {days} дн. · як змінювався трафік")

    # Dedicated plot axes — ONLY this has data scales
    plot_ax = fig.add_axes([0.14, 0.30, 0.74, 0.50])
    plot_ax.set_facecolor(CARD)
    for spine in ("top", "right"):
        plot_ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        plot_ax.spines[spine].set_color(GRID)
    plot_ax.tick_params(colors=MUTED, labelsize=8)
    plot_ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    plot_ax.set_axisbelow(True)

    if not rows:
        plot_ax.set_xticks([])
        plot_ax.set_yticks([])
        plot_ax.text(0.5, 0.5, "Немає денних даних", ha="center", va="center", color=MUTED)
    else:
        x = list(range(len(rows)))
        users = [int(r.get("users") or 0) for r in rows]
        sessions = [int(r.get("sessions") or 0) for r in rows]
        labels = [str(r.get("label") or "") for r in rows]
        plot_ax.fill_between(x, users, color=ACCENT_SOFT, alpha=0.85)
        plot_ax.plot(x, users, color=ACCENT, linewidth=2.4, marker="o", markersize=5, label="Користувачі")
        plot_ax.plot(
            x,
            sessions,
            color=GOLD,
            linewidth=2.0,
            marker="s",
            markersize=4,
            label="Сесії",
        )
        ymax = max(max(users + sessions), 1)
        plot_ax.set_ylim(0, ymax * 1.25)
        plot_ax.set_xlim(-0.4, len(x) - 0.6)
        step = max(1, len(labels) // 6)
        plot_ax.set_xticks(x[::step])
        plot_ax.set_xticklabels(labels[::step])
        # integer-ish y ticks
        plot_ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True, nbins=6))
        plot_ax.legend(frameon=False, fontsize=9, loc="upper left")

    _glossary(
        ax,
        [
            "Лінія «Користувачі» — скільки різних людей за день.",
            "Лінія «Сесії» — скільки разів заходили. Якщо сесій більше за користувачів — "
            "хтось заходив кілька разів.",
        ],
    )
    _footer(fig)
    return _fig_bytes(fig)


def render_engagement_chart(kpis: dict[str, str], *, days: int) -> bytes:
    fig, ax = _blank_fig()
    _header(ax, "3 · Залученість", f"Останні {days} дн. · наскільки «живі» візити")

    try:
        sessions = float(kpis.get("sessions") or 0)
        engaged = float(kpis.get("engagedSessions") or 0)
        users = float(kpis.get("activeUsers") or 0)
        views = float(kpis.get("pageViews") or 0)
    except (TypeError, ValueError):
        sessions = engaged = users = views = 0

    other = max(sessions - engaged, 0)
    if sessions <= 0:
        ax.text(0.5, 0.55, "Немає сесій за період", ha="center", color=MUTED, fontsize=12)
    else:
        donut = fig.add_axes([0.25, 0.42, 0.50, 0.35])
        donut.set_facecolor(BG)
        donut.pie(
            [max(engaged, 0.001), max(other, 0.001)],
            colors=[ACCENT, ZERO],
            startangle=90,
            wedgeprops={"width": 0.48, "edgecolor": BG, "linewidth": 4},
        )
        pct = 100.0 * engaged / sessions
        donut.text(0, 0.08, f"{pct:.0f}%", ha="center", va="center", fontsize=26, fontweight="700", color=INK)
        donut.text(0, -0.16, "залучених\nсесій", ha="center", va="center", fontsize=10, color=MUTED)

        metrics = [
            (f"{_fmt_int(engaged)} / {_fmt_int(sessions)}", "Залучені / усі сесії"),
            (f"{(views / sessions):.1f}" if sessions else "—", "Сторінок за візит"),
            (f"{(sessions / users):.1f}" if users else "—", "Візитів на людину"),
        ]
        for i, (val, lab) in enumerate(metrics):
            x = 0.06 + i * 0.31
            ax.add_patch(
                FancyBboxPatch(
                    (x, 0.26),
                    0.28,
                    0.12,
                    boxstyle="round,pad=0.01,rounding_size=0.018",
                    transform=ax.transAxes,
                    facecolor=CARD,
                    edgecolor=GRID,
                    clip_on=False,
                )
            )
            ax.text(
                x + 0.14,
                0.335,
                val,
                transform=ax.transAxes,
                ha="center",
                fontsize=13,
                fontweight="700",
                color=INK,
            )
            ax.text(
                x + 0.14,
                0.285,
                lab,
                transform=ax.transAxes,
                ha="center",
                fontsize=7.5,
                color=MUTED,
            )

    _glossary(
        ax,
        [
            "Сесія — один візит на сайт (відкрили сторінку і ходили по ній).",
            "Залучена сесія — візит, де людина затрималась або клікала "
            "(не «зайшла на секунду і вийшла»). Вищий % — краще.",
        ],
    )
    _footer(fig)
    return _fig_bytes(fig)


def render_top_pages_chart(top_pages: list[dict[str, Any]], *, days: int) -> bytes:
    pages = [p for p in (top_pages or []) if int(float(p.get("views") or 0)) > 0][:7]
    fig, ax = _blank_fig()
    _header(ax, "6 · Популярні сторінки", f"Останні {days} дн. · що дивились найчастіше")

    if not pages:
        ax.text(0.5, 0.55, "Немає переглядів", ha="center", color=MUTED, fontsize=12)
    else:
        max_v = max(int(float(p.get("views") or 0)) for p in pages) or 1
        for i, p in enumerate(pages):
            y = CONTENT_TOP - 0.02 - i * 0.08
            views_n = int(float(p.get("views") or 0))
            users_n = int(float(p.get("users") or 0))
            label = _friendly_path(str(p.get("path") or "/"))
            ax.text(
                0.05,
                y + 0.025,
                f"{i + 1}. {label}",
                transform=ax.transAxes,
                fontsize=10,
                color=INK,
                fontweight="600",
                va="center",
            )
            ax.text(
                0.95,
                y + 0.025,
                f"{_fmt_int(views_n)} · {_fmt_int(users_n)} люд.",
                transform=ax.transAxes,
                fontsize=9,
                color=MUTED,
                ha="right",
                va="center",
            )
            ax.add_patch(
                FancyBboxPatch(
                    (0.05, y - 0.012),
                    0.90,
                    0.016,
                    boxstyle="round,pad=0.001,rounding_size=0.004",
                    transform=ax.transAxes,
                    facecolor=GRID,
                    edgecolor="none",
                    clip_on=False,
                )
            )
            ax.add_patch(
                FancyBboxPatch(
                    (0.05, y - 0.012),
                    0.90 * (views_n / max_v),
                    0.016,
                    boxstyle="round,pad=0.001,rounding_size=0.004",
                    transform=ax.transAxes,
                    facecolor=ACCENT,
                    edgecolor="none",
                    clip_on=False,
                )
            )

    _glossary(
        ax,
        [
            "Перегляд — відкриття сторінки. Користувач — скільки різних людей її бачили.",
            "Якщо топ — головна і каталог, а товарів мало, варто перевірити картки товарів.",
        ],
    )
    _footer(fig)
    return _fig_bytes(fig)


def render_revenue_chart(
    revenue: dict[str, str],
    funnel: list[dict[str, Any]],
    *,
    days: int,
) -> bytes:
    fig, ax = _blank_fig()
    _header(ax, "7 · Продажі", f"Останні {days} дн. · гроші та покупки з GA4")

    purchases = _fmt_int(revenue.get("ecommercePurchases", "0"))
    rev = _fmt_money(revenue.get("purchaseRevenue", "0"))
    avg = _fmt_money(revenue.get("averagePurchaseRevenue", "0"))
    by_event = {r.get("event"): int(r.get("events") or 0) for r in (funnel or [])}
    view_n = by_event.get("view_item", 0)
    cart_n = by_event.get("add_to_cart", 0)
    purch_evt = by_event.get("purchase", 0)
    cvr = f"{(100.0 * purch_evt / view_n):.1f}%" if view_n else "—"

    big = [
        (rev, "Виручка, грн", "скільки грошей принесли покупки", GOLD),
        (purchases, "Покупки", "скільки оформлених замовлень у GA4", ACCENT),
        (avg, "Середній чек", "середня сума однієї покупки", ACCENT),
        (cvr, "Конверсія перегляд→покупка", "% людей, що купили після перегляду", ACCENT),
    ]
    for i, (val, lab, hint, color) in enumerate(big):
        y = CONTENT_TOP - 0.02 - i * 0.135
        ax.add_patch(
            FancyBboxPatch(
                (0.05, y - 0.11),
                0.90,
                0.12,
                boxstyle="round,pad=0.01,rounding_size=0.02",
                transform=ax.transAxes,
                facecolor=CARD,
                edgecolor=color if i == 0 else GRID,
                linewidth=1.6 if i == 0 else 1.0,
                clip_on=False,
            )
        )
        ax.text(
            0.09,
            y - 0.03,
            val,
            transform=ax.transAxes,
            fontsize=20,
            fontweight="700",
            color=INK,
            va="center",
        )
        ax.text(
            0.09,
            y - 0.065,
            lab,
            transform=ax.transAxes,
            fontsize=11,
            color=INK,
            fontweight="600",
            va="center",
        )
        ax.text(
            0.09,
            y - 0.09,
            hint,
            transform=ax.transAxes,
            fontsize=8,
            color=MUTED,
            va="center",
        )

    ax.text(
        0.05,
        GLOSS_TOP + 0.03,
        f"Події воронки: перегляд {view_n} · у кошик {cart_n} · покупка {purch_evt}",
        transform=ax.transAxes,
        fontsize=8,
        color=MUTED,
    )

    _glossary(
        ax,
        [
            "Виручка і покупки тут — з Google Analytics (подія purchase).",
            "Можуть трохи відрізнятись від адмінки магазину, якщо хтось пішов "
            "без сторінки «дякуємо» або подія не встигла відправитись.",
        ],
    )
    _footer(fig)
    return _fig_bytes(fig)


def render_realtime_chart(data: dict[str, Any]) -> bytes:
    screens = [s for s in (data.get("screens") or []) if int(s.get("users") or 0) > 0][:7]
    total = int(data.get("active_users") or sum(int(s.get("users") or 0) for s in screens))

    fig, ax = _blank_fig()
    _header(ax, "Зараз на сайті", f"Realtime · приблизно останні 30 хв · {total} онлайн")

    if not screens:
        ax.text(0.5, 0.55, "Зараз нікого на сайті", ha="center", color=MUTED, fontsize=13)
    else:
        max_u = max(int(s.get("users") or 0) for s in screens) or 1
        for i, s in enumerate(screens):
            y = CONTENT_TOP - 0.02 - i * 0.075
            users = int(s.get("users") or 0)
            title = str(s.get("screen") or "")[:40]
            ax.text(0.05, y + 0.02, title, transform=ax.transAxes, fontsize=10, color=INK, va="center")
            ax.text(
                0.95,
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
                    (0.05, y - 0.018),
                    0.90,
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
                    (0.05, y - 0.018),
                    0.90 * (users / max_u),
                    0.014,
                    boxstyle="round,pad=0.001,rounding_size=0.004",
                    transform=ax.transAxes,
                    facecolor=ACCENT,
                    edgecolor="none",
                    clip_on=False,
                )
            )

    _glossary(
        ax,
        [
            "Realtime показує, хто на сайті просто зараз (не за тиждень).",
            "Цифри оновлюються з невеликою затримкою Google Analytics.",
        ],
    )
    _footer(fig)
    return _fig_bytes(fig)


def build_dashboard_photos(dashboard: dict[str, Any]) -> list[tuple[str, bytes]]:
    days = int(dashboard.get("days") or 7)
    kpis = dashboard.get("kpis") or {}
    revenue = dashboard.get("revenue") or {}
    funnel = dashboard.get("funnel") or []
    return [
        ("01_traffic.png", render_kpi_table(kpis, revenue, days=days)),
        ("02_daily.png", render_daily_trend_chart(dashboard.get("daily") or [], days=days)),
        ("03_engagement.png", render_engagement_chart(kpis, days=days)),
        ("04_funnel.png", render_funnel_chart(funnel, days=days)),
        ("05_sources.png", render_sources_chart(dashboard.get("sources") or [], days=days)),
        ("06_pages.png", render_top_pages_chart(dashboard.get("top_pages") or [], days=days)),
        ("07_sales.png", render_revenue_chart(revenue, funnel, days=days)),
    ]


def _social_caption_line(days: int) -> str:
    """
    One line of social totals for the album caption.

    The slide alone is not enough: an album is read caption-first, and a
    number that appears only in the eighth picture is a number nobody sees.
    Silent by design when there is nothing collected yet.
    """
    try:
        from social.services.video_metrics import weekly_summary

        totals = weekly_summary(days=days)
        if not totals:
            return ""
        views = sum(d["views"] for d in totals.values() if d["views_known"])
        likes = sum(d["likes"] for d in totals.values())
        best = max(
            (kv for kv in totals.items() if kv[1]["views_known"]),
            key=lambda kv: kv[1]["views"],
            default=None,
        )
        line = f"📱 Соцмережі: {_fmt_int(views)} переглядів · {_fmt_int(likes)} ❤"
        if best:
            from social.models import VideoDelivery

            labels = dict(VideoDelivery.Platform.choices)
            line += f" · найкраще {labels.get(best[0], best[0])}"
        return line
    except Exception:
        return ""


def build_caption(dashboard: dict[str, Any], *, slides: int = 7) -> str:
    """
    `slides` is passed rather than assumed: the album grew a social-networks
    slide that is appended only when there are metrics to show, so the count
    is not fixed and a hardcoded one would be wrong half the time.
    """
    days = int(dashboard.get("days") or 7)
    k = dashboard.get("kpis") or {}
    r = dashboard.get("revenue") or {}
    funnel = dashboard.get("funnel") or []
    purch = next((x for x in funnel if x.get("event") == "purchase"), None)
    purch_events = purch.get("events") if purch else 0

    lines = [
        f"GA4 · останні {days} дн. · {slides} слайдів",
        f"👥 {_fmt_int(k.get('activeUsers'))} корист. · "
        f"{_fmt_int(k.get('sessions'))} сесій · "
        f"{_fmt_int(k.get('pageViews'))} перегл.",
        f"🛒 Покупки: {_fmt_int(r.get('ecommercePurchases'))} · "
        f"виручка {_fmt_money(r.get('purchaseRevenue'))} грн · "
        f"purchase: {_fmt_int(purch_events)}",
    ]
    social = _social_caption_line(days)
    if social:
        lines.append(social)
    lines.append("Внизу кожного фото — коротке пояснення простими словами.")
    return "\n".join(lines)


def build_realtime_caption(data: dict[str, Any]) -> str:
    total = int(data.get("active_users") or 0)
    return f"Realtime GA4 (~30 хв)\nЗараз онлайн: {total}"
