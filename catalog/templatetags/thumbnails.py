"""Template access to catalog.thumbnails.

    {% load thumbnails %}
    <img src="{{ article.image|thumb:400 }}"
         srcset="{{ article.image|thumb:400 }} 400w, {{ article.image|thumb:800 }} 800w"
         sizes="(max-width: 600px) 92vw, 376px" ...>
"""

from django import template

from catalog.thumbnails import thumbnail_url

register = template.Library()


@register.filter(name="thumb")
def thumb(field, width):
    """URL of a WebP copy of ``field`` at most ``width`` px wide (original on failure)."""
    return thumbnail_url(field, width)
