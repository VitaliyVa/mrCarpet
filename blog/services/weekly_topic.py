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

    target = _usable_target(topic.target_path)
    if target:
        prompt = (
            f"{prompt} Зроби в тексті природне посилання на {target} "
            f"там, де читачеві справді час подивитись товар."
        )

    stocked = _stocked_materials()
    if stocked:
        # Otherwise the article recommends what the shop does not sell. The
        # first drafts advised cotton and nylon rugs; the catalogue has
        # neither, so the piece would have ranked and sent the reader
        # elsewhere.
        prompt = (
            f"{prompt} У порадах згадуй лише матеріали, які є в магазині: "
            f"{stocked}. Не радь шерсть, бавовну, шовк чи нейлон."
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


def _usable_target(path: str) -> str:
    """
    The category to link to, or the general catalogue if it is empty.

    An article that ranks and lands the reader on a category with no products
    is worse than no article: they learn the shop has none of what they
    searched for. Checked at generation time rather than fixed in the seed
    list, so a category that fills up starts being linked again on its own.
    """
    path = (path or "").strip()
    if not path or "/categorie/" not in path:
        return path

    slug = path.rstrip("/").rsplit("/", 1)[-1]
    try:
        from catalog.models import ProductCategory

        category = ProductCategory.objects.filter(slug=slug).first()
        if category and category.products.exists():
            return path
    except Exception:
        logger.info("category check failed for %s", path)
        return path

    logger.info("category %s is empty, linking to the catalogue instead", slug)
    return "/catalog/"


def _stocked_materials() -> str:
    """What the shop actually sells, for the prompt to stay inside."""
    try:
        from catalog.models import ProductSpecification

        values = (
            ProductSpecification.objects.filter(
                specification__title__in=("Склад килима", "Основа")
            )
            .values_list("spec_value__title", flat=True)
            .distinct()
        )
        names = sorted({(v or "").strip() for v in values if (v or "").strip()})
        return ", ".join(names)
    except Exception:
        return ""
