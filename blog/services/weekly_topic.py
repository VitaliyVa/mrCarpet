"""
One article a week, from the top of the topic queue.

Publishes on its own, by the owner's decision. Two things follow from that,
and both are load-bearing.

First, the known failure modes are handled before the text exists rather
than caught after: the prompt is limited to materials the catalogue actually
stocks, empty target categories are swapped out, and the arithmetic rule is
spelled out — the first batch of drafts got a bed-sized rug wrong by 60 cm
by adding the margin to one side only.

Second, the Telegram alert carries the opening of the article, not just a
link. Nobody opens an admin panel to check something that already published;
they might read three lines in a chat they already have open. That is the
only review this pipeline gets, so it has to cost nothing.

Set AUTO_PUBLISH to False to go back to drafts.
"""

from __future__ import annotations

import logging

from django.utils import timezone

logger = logging.getLogger(__name__)

SITE = "https://mrcarpet24.com"

#: Publish without waiting for a human. The trade is deliberate: no post
#: sits unread for a week, and no post gets a second pair of eyes either.
AUTO_PUBLISH = True


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

    if AUTO_PUBLISH:
        from blog.models import Article

        article = Article.objects.filter(pk=article_id).first()
        if article:
            article.status = Article.Status.PUBLISHED
            article.save()

    # Marked used regardless of outcome. Leaving it pending would hand the
    # same topic to next week's run.
    topic.status = ArticleTopic.Status.USED
    topic.used_at = timezone.now()
    topic.article_id = article_id
    topic.save(update_fields=["status", "used_at", "article"])

    if notify:
        remaining = ArticleTopic.objects.filter(
            status=ArticleTopic.Status.PENDING
        ).count()
        _tell_staff(_alert_text(article_id, article_title, remaining))

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


#: How much of the article to put in the chat message. Enough to catch a wrong
#: number or an off-catalogue recommendation while scrolling; short enough
#: that it is actually read.
PREVIEW_CHARS = 600


def _alert_text(article_id: int, title: str, remaining: int) -> str:
    """
    What goes to the staff chat.

    Carries the opening of the article rather than only a link, because the
    post is already live: a link asks someone to go and check, and nobody
    does. Three lines in a chat that is already open sometimes get read, and
    that is the entire review this pipeline has.
    """
    import re

    from blog.models import Article

    article = Article.objects.filter(pk=article_id).first()
    published = bool(article and article.is_public)

    preview = ""
    if article:
        plain = re.sub(r"<[^>]+>", " ", article.description or "")
        plain = re.sub(r"\s+", " ", plain).strip()
        preview = plain[:PREVIEW_CHARS]
        if len(plain) > PREVIEW_CHARS:
            preview += "…"

    head = "✅ Стаття тижня опублікована" if published else "📝 Чернетка статті тижня"
    action = "Виправити або зняти" if published else "Прочитати й опублікувати"

    parts = [f"{head}\n{title}"]
    if published and article:
        parts.append(f"{SITE}{article.get_absolute_url()}")
    if preview:
        parts.append(f"\n{preview}")
    parts.append(
        f"\n{action}: {SITE}/admin/blog/article/{article_id}/change/"
        f"\nТем у черзі: {remaining}"
    )
    return "\n".join(parts)
