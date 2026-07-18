"""Render campaign HTML inside branded email shell."""

from __future__ import annotations

from django.template import Context, Template
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from project.email_branding import brand_context
from project.newsletter import unsubscribe_absolute_url


def personalize_body(body_html: str, *, unsubscribe_url: str) -> str:
    html = body_html or ""
    return html.replace("{{unsubscribe_url}}", unsubscribe_url)


def render_campaign_email(campaign, *, unsubscribe_url: str) -> str:
    """Full HTML for one recipient (or preview)."""
    inner = personalize_body(campaign.body_html, unsubscribe_url=unsubscribe_url)
    # Allow Django {{ }} only for known vars if any remain
    try:
        inner = Template(inner).render(
            Context({"unsubscribe_url": unsubscribe_url})
        )
    except Exception:
        pass
    ctx = brand_context(
        eyebrow="Розсилка",
        preheader=campaign.preheader or campaign.subject or "",
        content_html=inner,
    )
    return render_to_string("emails/base.html", ctx)


def render_campaign_preview(campaign) -> str:
    return render_campaign_email(
        campaign, unsubscribe_url="#unsubscribe-preview"
    )


def render_campaign_for_subscription(campaign, subscription) -> tuple[str, str]:
    """Returns (html, plain_text)."""
    unsub = unsubscribe_absolute_url(subscription)
    html = render_campaign_email(campaign, unsubscribe_url=unsub)
    plain = strip_tags(html)
    plain = "\n".join(line.strip() for line in plain.splitlines() if line.strip())
    plain += f"\n\nВідписатися: {unsub}"
    return html, plain
