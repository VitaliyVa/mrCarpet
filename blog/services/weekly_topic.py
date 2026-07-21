"""
One drafted article a week, from the top of the topic queue.

Generates and stops. It does not publish, and that is deliberate: Google's
spam policy names scaled content abuse — pages produced in bulk mainly for
search — and the penalty lands on the domain, not the post. A human reading
the draft before it goes live is what separates a blog from that.

So the machine does the part machines are good at (never forgetting, never
running out of topics) and leaves the judgement.
"""

from __future__ import annotations

import logging

from django.utils import timezone

logger = logging.getLogger(__name__)

SITE = "https://mrcarpet24.com"


def generate_next(*, notify: bool = True) -> dict:
    """
    Turn the highest-ranked pending topic into a draft article.

    Returns {"ok", "topic", "article_id"?, "error"?}. Never raises: this runs
    unattended, and a failed week should cost a post, not the scheduler.
    """
    from blog.models import ArticleTopic
    from blog.services.article_generate import ReplicateArticleService

    topic = ArticleTopic.next_pending()
    if topic is None:
        _tell_staff(
            "📭 Черга тем для блогу порожня.\n"
            "Додати нові: /admin/blog/articletopic/"
        )
        return {"ok": False, "error": "queue is empty"}

    # The brief and the target page are what make the piece worth publishing:
    # a topic alone produces something generic that links nowhere.
    prompt = topic.title
    if topic.brief:
        prompt = f"{topic.title}. {topic.brief}"
    if topic.target_path:
        prompt = (
            f"{prompt} Зроби в тексті природне посилання на {topic.target_path} "
            f"там, де читачеві справді час подивитись товар."
        )

    try:
        result = ReplicateArticleService().generate_and_create(prompt)
    except Exception as exc:
        logger.exception("weekly article generation failed for topic %s", topic.pk)
        _tell_staff(
            f"⚠️ Не вдалось згенерувати статтю тижня\n"
            f"Тема: {topic.title}\n{exc}"
        )
        return {"ok": False, "topic": topic.title, "error": str(exc)}

    article_id = result.article_id
    article_title = result.title

    # Marked used even though it is only a draft. Leaving it pending would
    # hand the same topic to next week's run while this draft sits unread.
    topic.status = ArticleTopic.Status.USED
    topic.used_at = timezone.now()
    topic.article_id = article_id
    topic.save(update_fields=["status", "used_at", "article"])

    if notify:
        remaining = ArticleTopic.objects.filter(
            status=ArticleTopic.Status.PENDING
        ).count()
        link = f"{SITE}/admin/blog/article/{article_id}/change/"
        _tell_staff(
            f"📝 Чернетка статті тижня готова\n"
            f"{article_title}\n\n"
            f"Прочитати, виправити й опублікувати:\n{link}\n\n"
            f"Тем у черзі лишилось: {remaining}"
        )

    return {"ok": True, "topic": topic.title, "article_id": article_id}


def _tell_staff(text: str) -> None:
    try:
        from social.services.comment_notify import notify_staff_text

        notify_staff_text(text)
    except Exception:
        logger.info("weekly blog notification failed")
