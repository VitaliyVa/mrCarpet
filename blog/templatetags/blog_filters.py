from django import template
from django.template.defaultfilters import linebreaks
from django.utils.safestring import mark_safe

from blog.services.article_render import reading_minutes, render_article
from blog.services.html_sanitize import looks_like_html, sanitize_article_html
from blog.services.product_cards import expand_product_blocks
from blog.services.topics import topic_for

register = template.Library()


@register.filter(name="article_body")
def article_body(value):
    """HTML CMS body → allowlist sanitize + live product cards; plain text → linebreaks."""
    if not value:
        return ""
    text = str(value)
    if looks_like_html(text):
        return mark_safe(expand_product_blocks(sanitize_article_html(text)))
    return linebreaks(text)


@register.simple_tag
def article_parts(article):
    """Body with heading ids + table of contents + reading time, in one pass."""
    return render_article(getattr(article, "description", "") or "")


@register.filter(name="reading_time")
def reading_time(article):
    """Minutes to read, never less than one."""
    return reading_minutes(getattr(article, "description", "") or "")


@register.filter(name="article_topic")
def article_topic(article):
    return topic_for(getattr(article, "title", "") or "")


@register.filter(name="uk_minutes")
def uk_minutes(value):
    """«1 хвилина», «3 хвилини», «5 хвилин»."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return ""
    if n % 10 == 1 and n % 100 != 11:
        word = "хвилина"
    elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        word = "хвилини"
    else:
        word = "хвилин"
    return f"{n} {word}"
