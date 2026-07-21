"""
GA4 slides for the Telegram album.

Every slide is the same shape — eyebrow, one headline number, ranked rows,
footnote — because eight pictures arriving together are read as one document
and a different layout per slide makes the reader re-learn the page each
time. Shared primitives live in project.chart_style.

Two chart types were deliberately dropped in the redesign: the polygon funnel
and the donuts. Both spend a lot of ink on shape rather than on comparison —
a funnel drawn as a trapezoid encodes its numbers in an area nobody can read,
and a two-slice donut is a percentage that would be clearer as a bar.
"""

from __future__ import annotations

from typing import Any

from project.chart_style import (
    ACCENT,
    BAND_BOTTOM,
    BAND_TOP,
    BG,
    FAINT,
    GOLD,
    INK,
    LEFT,
    MUTED,
    RIGHT,
    bar,
    canvas,
    empty,
    eyebrow,
    fmt_int,
    fmt_money,
    footnote,
    headline,
    png,
    row_label,
    rows_band,
    sub_label,
    track,
)

FUNNEL_STEPS = (
    ("view_item", "Перегляд товару"),
    ("add_to_cart", "Додали в кошик"),
    ("view_cart", "Відкрили кошик"),
    ("begin_checkout", "Оформлення"),
    ("add_shipping_info", "Доставка"),
    ("add_payment_info", "Спосіб оплати"),
    ("purchase", "Покупка"),
)

SOURCE = "mr.Carpet · Google Analytics 4"


def _human_source(source: str, medium: str) -> str:
    s = (source or "").strip() or "(not set)"
    m = (medium or "").strip() or "(not set)"
    if s in ("(not set)", "not set", "(none)") and m in ("(not set)", "not set", "(none)"):
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


def _num(raw: Any) -> float:
    try:
        return float(raw or 0)
    except (TypeError, ValueError):
        return 0.0


def _ranked_rows(ax, rows: list[tuple[str, int, str]], *, peak: int) -> None:
    """
    name / value / sub-line, one band each.

    The single row primitive behind five of the slides. Value is right-aligned
    to the margin, which is what keeps a long label from pushing a number off
    the canvas.
    """
    row_h = rows_band(len(rows))
    y = BAND_TOP
    for i, (label, value, sub) in enumerate(rows):
        centre = y - row_h / 2
        row_label(ax, centre + row_h * 0.22, label, fmt_int(value))
        track(ax, centre - row_h * 0.10)
        if value > 0:
            bar(ax, centre - row_h * 0.10, value / (peak or 1), rank=i)
        if sub:
            sub_label(ax, centre - row_h * 0.30, sub)
        y -= row_h


# ---- 1 · traffic ------------------------------------------------------


def render_kpi_table(
    kpis: dict[str, str],
    revenue: dict[str, str],
    *,
    days: int,
    top_pages: list[dict[str, Any]] | None = None,
) -> bytes:
    del top_pages
    fig, ax = canvas()
    eyebrow(ax, "Підсумок трафіку", f"Останні {days} дн. · хто заходив на сайт")

    sessions = _num(kpis.get("sessions"))
    engaged = _num(kpis.get("engagedSessions"))
    views = _num(kpis.get("pageViews"))

    headline(ax, fmt_int(kpis.get("activeUsers")), "різних людей на сайті")

    eng_pct = f"{(100 * engaged / sessions):.0f}%" if sessions else "—"
    per_sess = f"{(views / sessions):.1f}" if sessions else "—"
    stats = [
        (fmt_int(sessions), "Сесії", "скільки візитів"),
        (fmt_int(views), "Перегляди сторінок", "скільки сторінок відкрили"),
        (eng_pct, "Залученість", f"{fmt_int(engaged)} «живих» візитів"),
        (per_sess, "Сторінок за візит", "наскільки глибоко дивились"),
        (fmt_int(revenue.get("ecommercePurchases")), "Покупки", "деталі — слайд «Продажі»"),
    ]

    row_h = rows_band(len(stats))
    y = BAND_TOP
    for value, label, hint in stats:
        centre = y - row_h / 2
        row_label(ax, centre + row_h * 0.12, label, value)
        sub_label(ax, centre - row_h * 0.20, hint)
        ax.plot(
            [LEFT, RIGHT], [y - row_h, y - row_h],
            transform=ax.transAxes, color=FAINT, linewidth=0.8,
        )
        y -= row_h

    footnote(
        ax,
        [
            "Користувач — одна людина, скільки б разів вона не заходила.",
            "Сесія — один візит. Одна людина може мати кілька сесій.",
        ],
        source=SOURCE,
    )
    return png(fig)


# ---- 2 · daily trend --------------------------------------------------


def render_daily_trend_chart(daily: list[dict[str, Any]], *, days: int) -> bytes:
    rows = list(daily or [])
    fig, ax = canvas()
    eyebrow(ax, "Динаміка по днях", f"Останні {days} дн. · як змінювався трафік")

    if not rows:
        empty(ax, "Немає даних по днях")
        footnote(ax, ["Дані з'являться, щойно GA4 накопичить статистику."], source=SOURCE)
        return png(fig)

    users = [_num(r.get("users")) for r in rows]
    sessions = [_num(r.get("sessions")) for r in rows]
    labels = [str(r.get("date") or "")[-2:] for r in rows]

    headline(ax, fmt_int(sum(users)), "користувачів за період")

    plot = fig.add_axes([LEFT, BAND_BOTTOM, RIGHT - LEFT, BAND_TOP - BAND_BOTTOM - 0.06])
    plot.set_facecolor(BG)
    for spine in ("top", "right", "left"):
        plot.spines[spine].set_visible(False)
    plot.spines["bottom"].set_color(FAINT)
    plot.tick_params(colors=MUTED, labelsize=8, length=0)
    plot.yaxis.grid(True, color=FAINT, linewidth=0.8)
    plot.set_axisbelow(True)

    x = range(len(rows))
    plot.fill_between(x, users, color=ACCENT, alpha=0.12)
    plot.plot(x, users, color=ACCENT, linewidth=2.4, solid_capstyle="round")
    plot.plot(x, sessions, color=GOLD, linewidth=1.6, linestyle=(0, (3, 3)))

    plot.set_xticks(list(x))
    plot.set_xticklabels(labels, fontsize=7.5)
    plot.set_ylim(bottom=0)

    ax.text(
        LEFT, BAND_BOTTOM - 0.045, "— користувачі", transform=ax.transAxes,
        fontsize=9, color=ACCENT, fontweight="semibold", va="top",
    )
    ax.text(
        LEFT + 0.18, BAND_BOTTOM - 0.045, "-- сесії", transform=ax.transAxes,
        fontsize=9, color=GOLD, fontweight="semibold", va="top",
    )

    footnote(
        ax,
        [
            "Кожна точка — один день. Підпис знизу — число місяця.",
            "Сесій завжди більше або стільки ж, скільки користувачів.",
        ],
        source=SOURCE,
    )
    return png(fig)


# ---- 3 · engagement ---------------------------------------------------


def render_engagement_chart(kpis: dict[str, str], *, days: int) -> bytes:
    fig, ax = canvas()
    eyebrow(ax, "Залученість", f"Останні {days} дн. · наскільки «живі» візити")

    sessions = _num(kpis.get("sessions"))
    engaged = _num(kpis.get("engagedSessions"))
    views = _num(kpis.get("pageViews"))
    users = _num(kpis.get("activeUsers"))

    if sessions <= 0:
        empty(ax, "Немає сесій за період")
        footnote(ax, ["Залучена сесія — довша за 10 секунд або з дією."], source=SOURCE)
        return png(fig)

    pct = 100.0 * engaged / sessions
    headline(ax, f"{pct:.0f}%", "сесій були залученими")

    # A bar rather than the donut it replaced: this is one share of one
    # whole, and a bar shows it at a glance without a legend.
    track(ax, BAND_TOP + 0.02, height=0.022)
    bar(ax, BAND_TOP + 0.02, engaged / sessions, height=0.022)

    stats = [
        (f"{fmt_int(engaged)} / {fmt_int(sessions)}", "Залучені / усі сесії"),
        (f"{(views / sessions):.1f}", "Сторінок за візит"),
        (f"{(sessions / users):.1f}" if users else "—", "Візитів на людину"),
    ]
    row_h = rows_band(len(stats)) * 0.8
    y = BAND_TOP - 0.06
    for value, label in stats:
        centre = y - row_h / 2
        row_label(ax, centre, label, value)
        ax.plot(
            [LEFT, RIGHT], [y - row_h, y - row_h],
            transform=ax.transAxes, color=FAINT, linewidth=0.8,
        )
        y -= row_h

    footnote(
        ax,
        [
            "Залучена сесія — візит довший за 10 секунд, або з дією, "
            "або більш ніж з однією сторінкою.",
            "Решта — люди, які пішли одразу.",
        ],
        source=SOURCE,
    )
    return png(fig)


# ---- 4 · funnel -------------------------------------------------------


def render_funnel_chart(funnel: list[dict[str, Any]], *, days: int) -> bytes:
    by_event = {r.get("event"): int(_num(r.get("events"))) for r in (funnel or [])}
    values = [(lab, by_event.get(key, 0)) for key, lab in FUNNEL_STEPS]
    top = values[0][1] if values else 0

    fig, ax = canvas()
    eyebrow(ax, "Воронка продажів", f"Останні {days} дн. · шлях від перегляду до покупки")

    if not top:
        empty(ax, "Немає подій воронки")
        footnote(ax, ["Воронка з'явиться, щойно почнуться перегляди товарів."], source=SOURCE)
        return png(fig)

    purchases = by_event.get("purchase", 0)
    headline(ax, f"{(100.0 * purchases / top):.1f}%", f"з {fmt_int(top)} переглядів дійшли до покупки")

    # Bars against the first step, plus step-to-step retention. The old
    # trapezoid encoded the same numbers as an area, which is the one visual
    # channel people read worst.
    row_h = rows_band(len(values))
    y = BAND_TOP
    prev = None
    for i, (label, value) in enumerate(values):
        centre = y - row_h / 2
        row_label(ax, centre + row_h * 0.22, label, fmt_int(value))
        track(ax, centre - row_h * 0.10)
        if value > 0:
            bar(ax, centre - row_h * 0.10, value / top, rank=i)
        if prev is not None and prev > 0:
            sub_label(ax, centre - row_h * 0.30, f"дійшло {100.0 * value / prev:.0f}% з попереднього кроку")
        prev = value
        y -= row_h

    footnote(
        ax,
        [
            "Кожен рядок — скільки разів сталася подія, не скільки людей.",
            "Відсоток під смугою — скільки дійшло з попереднього кроку. "
            "Найбільше падіння показує, де саме люди йдуть.",
        ],
        source=SOURCE,
    )
    return png(fig)


# ---- 5 · sources ------------------------------------------------------


def render_sources_chart(sources: list[dict[str, Any]], *, days: int) -> bytes:
    rows = []
    for r in sources or []:
        sess = int(_num(r.get("sessions")))
        if sess <= 0:
            continue
        rows.append(
            (
                _human_source(str(r.get("source") or ""), str(r.get("medium") or "")),
                sess,
                int(_num(r.get("purchases"))),
            )
        )
    rows = rows[:6]

    fig, ax = canvas()
    eyebrow(ax, "Звідки приходять", f"Останні {days} дн. · як люди потрапляють на сайт")

    if not rows:
        empty(ax, "Немає даних про джерела")
        footnote(ax, ["Джерело — звідки прийшов відвідувач: Google, Instagram, посилання."], source=SOURCE)
        return png(fig)

    total = sum(r[1] for r in rows)
    peak = max(r[1] for r in rows)
    headline(ax, fmt_int(total), "сесій із цих джерел")

    _ranked_rows(
        ax,
        [
            (
                label[:34],
                sess,
                f"{100.0 * sess / total:.0f}% усіх"
                + (f" · {fmt_int(purch)} покупок" if purch else ""),
            )
            for label, sess, purch in rows
        ],
        peak=peak,
    )

    footnote(
        ax,
        [
            "«Прямі / невідомі» — GA4 не побачив ані реклами, ані посилання: "
            "закладка, інкогніто або месенджер без utm-міток.",
            "Щоденне відео має мітку daily-video — його видно окремим рядком.",
        ],
        source=SOURCE,
    )
    return png(fig)


# ---- 6 · pages --------------------------------------------------------


def render_top_pages_chart(top_pages: list[dict[str, Any]], *, days: int) -> bytes:
    pages = [p for p in (top_pages or []) if _num(p.get("views")) > 0][:7]
    fig, ax = canvas()
    eyebrow(ax, "Популярні сторінки", f"Останні {days} дн. · що дивились найчастіше")

    if not pages:
        empty(ax, "Немає переглядів")
        footnote(ax, ["Сторінки з'являться, щойно на сайт почнуть заходити."], source=SOURCE)
        return png(fig)

    peak = max(int(_num(p.get("views"))) for p in pages)
    headline(ax, fmt_int(sum(_num(p.get("views")) for p in pages)), "переглядів цих сторінок")

    _ranked_rows(
        ax,
        [
            (
                f"{i + 1}. {_friendly_path(str(p.get('path') or '/'))}",
                int(_num(p.get("views"))),
                f"{fmt_int(p.get('users'))} різних людей",
            )
            for i, p in enumerate(pages)
        ],
        peak=peak,
    )

    footnote(
        ax,
        [
            "Перегляд — одне відкриття сторінки. Одна людина може відкрити "
            "ту саму сторінку кілька разів.",
        ],
        source=SOURCE,
    )
    return png(fig)


# ---- 7 · revenue ------------------------------------------------------


def render_revenue_chart(
    revenue: dict[str, str],
    funnel: list[dict[str, Any]],
    *,
    days: int,
) -> bytes:
    fig, ax = canvas()
    eyebrow(ax, "Продажі", f"Останні {days} дн. · гроші та покупки з GA4")

    by_event = {r.get("event"): int(_num(r.get("events"))) for r in (funnel or [])}
    view_n = by_event.get("view_item", 0)
    purch_evt = by_event.get("purchase", 0)
    cvr = f"{(100.0 * purch_evt / view_n):.1f}%" if view_n else "—"

    headline(ax, fmt_money(revenue.get("purchaseRevenue")), "грн виручки за період")

    stats = [
        (fmt_int(revenue.get("ecommercePurchases")), "Покупки", "оформлених замовлень у GA4"),
        (fmt_money(revenue.get("averagePurchaseRevenue")), "Середній чек", "середня сума однієї покупки"),
        (cvr, "Конверсія", "% переглядів товару, що стали покупкою"),
    ]
    row_h = rows_band(len(stats)) * 0.9
    y = BAND_TOP
    for value, label, hint in stats:
        centre = y - row_h / 2
        row_label(ax, centre + row_h * 0.12, label, value)
        sub_label(ax, centre - row_h * 0.20, hint)
        ax.plot(
            [LEFT, RIGHT], [y - row_h, y - row_h],
            transform=ax.transAxes, color=FAINT, linewidth=0.8,
        )
        y -= row_h

    footnote(
        ax,
        [
            "Ці цифри — з GA4, а не з адмінки. GA4 не бачить замовлень, "
            "оформлених телефоном чи в Direct, тож в адмінці їх зазвичай більше.",
        ],
        source=SOURCE,
    )
    return png(fig)


# ---- realtime ---------------------------------------------------------


def render_realtime_chart(data: dict[str, Any]) -> bytes:
    screens = [s for s in (data.get("screens") or []) if _num(s.get("users")) > 0][:7]
    total = int(_num(data.get("active_users")) or sum(_num(s.get("users")) for s in screens))

    fig, ax = canvas()
    eyebrow(ax, "Зараз на сайті", "Realtime · приблизно останні 30 хвилин")
    headline(ax, fmt_int(total), "людей онлайн")

    if not screens:
        empty(ax, "Зараз нікого на сайті")
        footnote(ax, ["Realtime показує приблизно останні 30 хвилин."], source=SOURCE)
        return png(fig)

    peak = max(int(_num(s.get("users"))) for s in screens)
    _ranked_rows(
        ax,
        [(str(s.get("screen") or "")[:34], int(_num(s.get("users"))), "") for s in screens],
        peak=peak,
    )

    footnote(
        ax,
        [
            "Realtime — приблизні дані за останні 30 хвилин, "
            "вони не збігаються зі звітами за день.",
        ],
        source=SOURCE,
    )
    return png(fig)


# ---- album ------------------------------------------------------------


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

    The slide alone is not enough: an album is read caption-first, so a number
    that lives only in the eighth picture is a number nobody sees. Silent by
    design when nothing has been collected yet.
    """
    try:
        from social.models import VideoDelivery
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
        line = f"📱 Соцмережі: {fmt_int(views)} переглядів · {fmt_int(likes)} ❤"
        if best:
            labels = dict(VideoDelivery.Platform.choices)
            line += f" · найкраще {labels.get(best[0], best[0])}"
        return line
    except Exception:
        return ""


def build_caption(dashboard: dict[str, Any], *, slides: int = 7) -> str:
    """
    `slides` is passed rather than assumed: the album grew a social-networks
    slide that is appended only when there are metrics, so the count is not
    fixed and a hardcoded one would be wrong half the time.
    """
    days = int(dashboard.get("days") or 7)
    k = dashboard.get("kpis") or {}
    r = dashboard.get("revenue") or {}
    funnel = dashboard.get("funnel") or []
    purch = next((x for x in funnel if x.get("event") == "purchase"), None)
    purch_events = purch.get("events") if purch else 0

    lines = [
        f"GA4 · останні {days} дн. · {slides} слайдів",
        f"👥 {fmt_int(k.get('activeUsers'))} корист. · "
        f"{fmt_int(k.get('sessions'))} сесій · "
        f"{fmt_int(k.get('pageViews'))} перегл.",
        f"🛒 Покупки: {fmt_int(r.get('ecommercePurchases'))} · "
        f"виручка {fmt_money(r.get('purchaseRevenue'))} грн · "
        f"purchase: {fmt_int(purch_events)}",
    ]
    social = _social_caption_line(days)
    if social:
        lines.append(social)
    lines.append("Внизу кожного фото — коротке пояснення простими словами.")
    return "\n".join(lines)


def build_realtime_caption(data: dict[str, Any]) -> str:
    total = int(_num(data.get("active_users")))
    return f"Realtime GA4 (~30 хв)\nЗараз онлайн: {total}"
