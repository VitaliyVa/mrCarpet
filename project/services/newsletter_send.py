"""Test + mass send for NewsletterCampaign via Brevo SMTP."""

from __future__ import annotations

import logging
import threading
import time

from django.db import close_old_connections, transaction
from django.utils import timezone

from project.models import NewsletterCampaign, NewsletterDelivery, Subscription
from project.newsletter import unsubscribe_absolute_url
from project.services.newsletter_render import (
    render_campaign_for_subscription,
    render_campaign_preview,
)
from project.smtp_utils import send_smtp_mail

logger = logging.getLogger(__name__)

# Soft guard for Brevo free tier (~300/day)
DAILY_SOFT_LIMIT = 280
SEND_DELAY_SEC = 0.7


class NewsletterSendError(Exception):
    pass


def active_subscribers_count() -> int:
    return Subscription.objects.filter(is_active=True).count()


def send_campaign_test(campaign: NewsletterCampaign, to_email: str) -> None:
    to_email = (to_email or "").strip()
    if not to_email:
        raise NewsletterSendError("Вкажіть test email")
    if not (campaign.body_html or "").strip():
        raise NewsletterSendError("Спочатку згенеруйте або вставте HTML")

    # Use a dummy/active sub for unsubscribe URL if possible
    sub = (
        Subscription.objects.filter(email__iexact=to_email).first()
        or Subscription.objects.filter(is_active=True).first()
    )
    if sub:
        html, plain = render_campaign_for_subscription(campaign, sub)
        unsub = unsubscribe_absolute_url(sub)
    else:
        html = render_campaign_preview(campaign)
        plain = "Тестова розсилка mr.Carpet"
        unsub = "#unsubscribe-preview"

    headers = {
        "List-Unsubscribe": f"<{unsub}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }
    ok = send_smtp_mail(
        subject=f"[TEST] {campaign.subject}",
        message=plain,
        recipient_list=[to_email],
        fail_silently=False,
        html_message=html,
        extra_headers=headers,
    )
    if not ok:
        raise NewsletterSendError("SMTP не відправив тестовий лист")
    campaign.test_email = to_email
    campaign.save(update_fields=["test_email", "updated_at"])


def enqueue_campaign_send(campaign_id: int) -> None:
    def _run():
        close_old_connections()
        try:
            _send_campaign_sync(campaign_id)
        except Exception:
            logger.exception("newsletter mass send failed campaign=%s", campaign_id)
        finally:
            close_old_connections()

    threading.Thread(
        target=_run, daemon=True, name=f"newsletter-send-{campaign_id}"
    ).start()


def _send_campaign_sync(campaign_id: int) -> None:
    campaign = NewsletterCampaign.objects.filter(pk=campaign_id).first()
    if not campaign:
        return
    if campaign.status == NewsletterCampaign.STATUS_SENT:
        return
    if not (campaign.body_html or "").strip():
        campaign.status = NewsletterCampaign.STATUS_FAILED
        campaign.save(update_fields=["status", "updated_at"])
        return

    subs = list(Subscription.objects.filter(is_active=True).order_by("id"))
    campaign.status = NewsletterCampaign.STATUS_SENDING
    campaign.recipients_total = len(subs)
    campaign.recipients_sent = 0
    campaign.recipients_failed = 0
    campaign.save(
        update_fields=[
            "status",
            "recipients_total",
            "recipients_sent",
            "recipients_failed",
            "updated_at",
        ]
    )

    sent = 0
    failed = 0
    for sub in subs:
        try:
            html, plain = render_campaign_for_subscription(campaign, sub)
            unsub = unsubscribe_absolute_url(sub)
            headers = {
                "List-Unsubscribe": f"<{unsub}>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            }
            ok = send_smtp_mail(
                subject=campaign.subject,
                message=plain,
                recipient_list=[sub.email],
                fail_silently=True,
                html_message=html,
                extra_headers=headers,
            )
            NewsletterDelivery.objects.update_or_create(
                campaign=campaign,
                subscription=sub,
                defaults={
                    "status": (
                        NewsletterDelivery.STATUS_SENT
                        if ok
                        else NewsletterDelivery.STATUS_FAILED
                    ),
                    "error": "" if ok else "SMTP send failed",
                },
            )
            if ok:
                sent += 1
            else:
                failed += 1
        except Exception as exc:
            failed += 1
            NewsletterDelivery.objects.update_or_create(
                campaign=campaign,
                subscription=sub,
                defaults={
                    "status": NewsletterDelivery.STATUS_FAILED,
                    "error": str(exc)[:2000],
                },
            )
            logger.exception("delivery failed campaign=%s sub=%s", campaign_id, sub.pk)

        NewsletterCampaign.objects.filter(pk=campaign_id).update(
            recipients_sent=sent,
            recipients_failed=failed,
        )
        time.sleep(SEND_DELAY_SEC)

    NewsletterCampaign.objects.filter(pk=campaign_id).update(
        status=NewsletterCampaign.STATUS_SENT,
        sent_at=timezone.now(),
        recipients_sent=sent,
        recipients_failed=failed,
    )


def start_mass_send(campaign: NewsletterCampaign) -> int:
    """Validate + enqueue. Returns recipient count."""
    if campaign.is_locked and campaign.status == NewsletterCampaign.STATUS_SENT:
        raise NewsletterSendError("Кампанію вже надіслано")
    if campaign.status == NewsletterCampaign.STATUS_SENDING:
        raise NewsletterSendError("Кампанія вже відправляється")
    if not (campaign.body_html or "").strip():
        raise NewsletterSendError("Немає HTML тіла")
    n = active_subscribers_count()
    if n == 0:
        raise NewsletterSendError("Немає активних підписників")
    if n > DAILY_SOFT_LIMIT:
        raise NewsletterSendError(
            f"Активних {n} > soft-ліміту {DAILY_SOFT_LIMIT}/день (Brevo). "
            "Зменшіть базу або підніміть ліміт у коді після апгрейду SMTP."
        )
    with transaction.atomic():
        locked = NewsletterCampaign.objects.select_for_update().get(pk=campaign.pk)
        if locked.status == NewsletterCampaign.STATUS_SENDING:
            raise NewsletterSendError("Кампанія вже відправляється")
        locked.status = NewsletterCampaign.STATUS_SENDING
        locked.save(update_fields=["status", "updated_at"])
    enqueue_campaign_send(campaign.pk)
    return n
