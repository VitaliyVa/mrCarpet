"""Build GA4 dashboard and deliver to Telegram (on-demand + weekly)."""

from __future__ import annotations

import logging
from typing import Any

from project.ga4_charts import build_caption, build_dashboard_photos
from project.ga4_client import Ga4ClientError, fetch_dashboard, ga4_configured
from project.telegram_api import send_media_group, send_message

logger = logging.getLogger(__name__)


def send_ga4_dashboard_report(
    *,
    days: int = 7,
    chat_id: str | None = None,
    message_thread_id=None,
    intro: str = "",
) -> dict[str, Any]:
    """
    Fetch GA4 dashboard, render PNGs, send Telegram album.
    Returns {ok, error?, caption?, photos_count?}.
    """
    days = max(1, min(int(days or 7), 30))
    if not ga4_configured():
        return {
            "ok": False,
            "error": "GA4 не налаштовано (GA4_PROPERTY_ID + credentials).",
        }

    try:
        data = fetch_dashboard(days)
        photos = build_dashboard_photos(data)
        # Today first — it is the slide most likely to be read, and its window
        # is fetched separately because it is not the album's period.
        from project.ga4_charts import build_today_photo

        today = build_today_photo()
        if today:
            photos.insert(0, today)
        # Same extra slide the on-demand report appends. Added in both places
        # rather than one, because these two paths already build their albums
        # independently — leaving it out here would mean the weekly report
        # silently lacks a slide the ad-hoc one has.
        from social.services.metrics_chart import build_social_photo

        social_photo = build_social_photo(days=days)
        if social_photo:
            photos.append(social_photo)
        caption = build_caption(data, slides=len(photos))
        if intro:
            caption = f"{intro}\n{caption}"
    except Ga4ClientError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:
        logger.exception("GA4 dashboard report failed")
        return {"ok": False, "error": f"Помилка звіту: {exc}"}

    if not photos:
        return {"ok": False, "error": "Немає зображень для звіту"}

    try:
        send_media_group(
            photos,
            caption=caption[:1024],
            chat_id=chat_id,
            message_thread_id=message_thread_id,
        )
    except Exception as exc:
        logger.exception("Telegram media send failed")
        return {"ok": False, "error": f"Telegram: {exc}"}

    return {
        "ok": True,
        "caption": caption,
        "photos_count": len(photos),
        "days": days,
        "summary": {
            "kpis": data.get("kpis"),
            "revenue": data.get("revenue"),
        },
    }


def send_weekly_ga4_report() -> dict[str, Any]:
    """Monday digest: last 7 days to configured notify chat."""
    from project.models import TelegramSettings

    settings = TelegramSettings.load()
    if not settings.is_configured:
        return {"ok": False, "error": "Telegram notify не налаштовано"}

    intro = "📅 Тижневий звіт mr.Carpet (автоматично, пн 10:00 Київ)"
    result = send_ga4_dashboard_report(
        days=7,
        chat_id=str(settings.chat_id).strip(),
        message_thread_id=(settings.message_thread_id or "").strip() or None,
        intro=intro,
    )
    if not result.get("ok"):
        try:
            send_message(
                f"⚠️ Тижневий GA4 звіт не вдався: {result.get('error')}",
                chat_id=str(settings.chat_id).strip(),
                message_thread_id=(settings.message_thread_id or "").strip() or None,
            )
        except Exception:
            pass
    return result
