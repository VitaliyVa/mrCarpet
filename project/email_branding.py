"""Shared branded HTML email shell (table layout for Outlook/Gmail/Apple Mail)."""
from __future__ import annotations

import html as html_lib
from typing import Any

from django.conf import settings
from django.template.loader import render_to_string


def site_url() -> str:
    return getattr(settings, "SITE_URL", "https://mrcarpet24.com").rstrip("/")


def absolute_static(path: str) -> str:
    path = path.lstrip("/")
    return f"{site_url()}/static/{path}"


def support_email() -> str:
    """Real inbox for humans (footer + Reply-To). Not the Brevo From address."""
    return (
        getattr(settings, "SUPPORT_EMAIL", "") or "mr.carpet.shop@gmail.com"
    ).strip()


def plain_text_footer() -> str:
    """Standard shop noreply + contact block for multipart plain bodies."""
    email = support_email()
    return (
        "\n\n---\n"
        "Це автоматичне повідомлення — відповідати на нього не потрібно.\n"
        f"З питань пишіть на {email} або на сайті {site_url().replace('https://', '')}."
    )


def with_plain_footer(body: str) -> str:
    text = (body or "").rstrip()
    footer = plain_text_footer()
    if footer.strip() in text:
        return text
    return f"{text}{footer}"


def brand_context(**extra) -> dict[str, Any]:
    base = {
        "site_url": site_url(),
        "logo_url": absolute_static("utils/assets/brand/email-logo.png"),
        "brand_name": "mr.Carpet",
        "support_email": support_email(),
        "year": __import__("datetime").datetime.now().year,
    }
    base.update(extra)
    return base


def render_branded_email(
    content_template: str,
    context: dict | None = None,
    *,
    eyebrow: str = "",
    preheader: str = "",
) -> str:
    """
    Render a content partial inside emails/base.html.
    content_template should only contain the inner body rows/blocks.
    """
    ctx = brand_context(**(context or {}))
    ctx["eyebrow"] = eyebrow
    ctx["preheader"] = preheader
    ctx["content_html"] = render_to_string(content_template, ctx)
    return render_to_string("emails/base.html", ctx)


def wrap_plain_body(
    body_text: str,
    *,
    title: str = "",
    eyebrow: str = "Повідомлення",
    preheader: str = "",
) -> str:
    """Wrap free-text (Telegram AI etc.) into branded HTML."""
    escaped = html_lib.escape(body_text or "").replace("\n", "<br>\n")
    ctx = brand_context(
        title=title or "Повідомлення від mr.Carpet",
        body_html=escaped,
        eyebrow=eyebrow,
        preheader=preheader or title,
    )
    ctx["content_html"] = render_to_string("emails/_plain_body.html", ctx)
    return render_to_string("emails/base.html", ctx)


def wrap_plain_email(
    body_text: str,
    *,
    title: str = "",
    eyebrow: str = "Повідомлення",
    preheader: str = "",
) -> tuple[str, str]:
    """Plain + HTML pair for free-text transactional emails."""
    plain = with_plain_footer(body_text or "")
    html = wrap_plain_body(
        body_text or "",
        title=title,
        eyebrow=eyebrow,
        preheader=preheader,
    )
    return plain, html
