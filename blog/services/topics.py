"""Blog topics, derived from the article title.

Article has no category field, and adding one would mean a migration and an
editor remembering to fill it for every post. The titles already say what an
article is about («Килимок у ванну…», «Чим чистити…»), so the topic is read
from there. First match wins, so the order below is the priority.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Topic:
    slug: str
    label: str
    emoji: str
    keywords: tuple[str, ...] = ()


TOPICS: tuple[Topic, ...] = (
    Topic(
        "kimnaty",
        "Килим у кімнату",
        "🏠",
        ("ванн", "кухн", "дитяч", "спальн", "вітальн", "передпок", "коридор", "балкон", "офіс"),
    ),
    Topic(
        "doglyad",
        "Догляд і чистка",
        "🧽",
        ("чистит", "чистк", "прати", "пранн", "догляд за", "доглядат", "пляма", "плями", "запах"),
    ),
    Topic(
        "materialy",
        "Матеріали",
        "🧶",
        ("поліпропілен", "поліестер", "джут", "вовн", "акрил", "віскоз", "матеріал", "основа"),
    ),
    Topic(
        "vybir",
        "Як вибрати",
        "📐",
        ("вибрати", "вибір", "розмір", "підібрати", "обрати"),
    ),
)

#: Everything that matched nothing above.
DEFAULT_TOPIC = Topic("porady", "Корисні поради", "💡")

ALL_TOPICS: tuple[Topic, ...] = TOPICS + (DEFAULT_TOPIC,)
_BY_SLUG = {t.slug: t for t in ALL_TOPICS}


def topic_for(title: str | None) -> Topic:
    text = (title or "").casefold()
    for topic in TOPICS:
        if any(word in text for word in topic.keywords):
            return topic
    return DEFAULT_TOPIC


def topic_by_slug(slug: str | None) -> Topic | None:
    return _BY_SLUG.get((slug or "").strip())
