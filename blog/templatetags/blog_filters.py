from django import template
from django.template.defaultfilters import linebreaks
from django.utils.safestring import mark_safe

from blog.services.html_sanitize import looks_like_html, sanitize_article_html

register = template.Library()


@register.filter(name="article_body")
def article_body(value):
    """HTML CMS body → allowlist sanitize + safe; plain text → linebreaks."""
    if not value:
        return ""
    text = str(value)
    if looks_like_html(text):
        return mark_safe(sanitize_article_html(text))
    return linebreaks(text)
