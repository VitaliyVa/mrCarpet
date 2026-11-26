import re

from django.core.paginator import InvalidPage, Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, render

from .models import Article
from .services.topics import ALL_TOPICS, topic_by_slug, topic_for

#: Articles per page. The list used to fetch every row and reverse it in
#: Python — fine at ten posts, a full table scan at a hundred.
PER_PAGE = 9

#: How many «Читайте також» cards sit under an article.
RELATED_COUNT = 3


def published_articles():
    """
    The only queryset the public side may use.

    Ordering comes from Meta, so it happens in SQL rather than by slicing the
    whole table backwards in memory. Scheduled articles (published_at in the
    future) stay out until their moment, see ArticleQuerySet.public.
    """
    return Article.objects.public()


def _topic_chips(titles_by_pk):
    """Topics that actually have articles, in the fixed order, with counts."""
    counts = {}
    for title in titles_by_pk.values():
        slug = topic_for(title).slug
        counts[slug] = counts.get(slug, 0) + 1
    return [
        {"topic": topic, "count": counts[topic.slug]}
        for topic in ALL_TOPICS
        if counts.get(topic.slug)
    ]


def blog(request):
    from django.urls import reverse

    from project.seo_jsonld import breadcrumb_graph, dumps_jsonld

    queryset = published_articles()

    # Topics are read from titles (see services/topics.py), so the filter
    # runs in Python over (pk, title) pairs. Case-insensitive matching of
    # Cyrillic in SQL is not portable (SQLite's LIKE folds ASCII only).
    titles_by_pk = dict(queryset.values_list("pk", "title"))
    chips = _topic_chips(titles_by_pk)
    active_topic = topic_by_slug(request.GET.get("tema"))
    if active_topic:
        queryset = queryset.filter(
            pk__in=[
                pk
                for pk, title in titles_by_pk.items()
                if topic_for(title).slug == active_topic.slug
            ]
        )

    paginator = Paginator(queryset, PER_PAGE)
    # a missing or empty ?page= is page 1; anything else invalid (999, abc)
    # is a page that does not exist: 404, not a copy of another page
    try:
        articles = paginator.page(request.GET.get("page") or 1)
    except InvalidPage:
        raise Http404("Сторінку не знайдено")

    # The newest post gets the wide card, on the unfiltered first page only:
    # in a topic view every card is already a pick.
    object_list = list(articles.object_list)
    featured = None
    if articles.number == 1 and not active_topic and object_list:
        featured, object_list = object_list[0], object_list[1:]

    crumbs = [("Головна", "/"), ("Блог", reverse("blog"))]
    return render(
        request,
        "blog.html",
        context={
            "articles": articles,
            "featured": featured,
            "cards": object_list,
            "page_obj": articles,
            "paginator": paginator,
            # Chips only help once there is more than one topic to pick from.
            "topic_chips": chips if len(chips) > 1 else [],
            "active_topic": active_topic,
            "total_count": len(titles_by_pk),
            # The detail page carried breadcrumbs in JSON-LD while the list
            # drew them only as HTML, so the trail Google saw stopped one
            # level short of the reader's.
            "breadcrumb_jsonld": dumps_jsonld(breadcrumb_graph(request, crumbs)),
        },
    )


def related_articles(article, limit=RELATED_COUNT):
    """Same topic first, then the newest. Never the article itself."""
    candidates = list(published_articles().exclude(pk=article.pk)[:24])
    topic = topic_for(article.title).slug
    same = [a for a in candidates if topic_for(a.title).slug == topic]
    rest = [a for a in candidates if a not in same]
    return (same + rest)[:limit]


#: A shop category link inside article HTML (relative or absolute).
_CATEGORY_LINK_RE = re.compile(r"/catalog/categorie/([\w-]+)/")


def catalog_cta_url(article) -> str:
    """Where «Перейти в каталог» under an article leads.

    The first shop category the article text links to (that is what the
    article is about), else the category its blog topic targets, else the
    whole catalog. Only categories that exist, so the button never 404s.
    """
    from catalog.models import ProductCategory

    slugs = _CATEGORY_LINK_RE.findall(article.description or "")
    if article.pk:
        for path in article.topics.values_list("target_path", flat=True):
            slugs += _CATEGORY_LINK_RE.findall(f"{path or ''}/")
    if slugs:
        found = {
            c.slug: c for c in ProductCategory.objects.filter(slug__in=set(slugs))
        }
        for slug in slugs:
            if slug in found:
                return found[slug].get_absolute_url()
    return "/catalog/"


def post(request, slug):
    from django.urls import reverse

    from project.seo_jsonld import article_graph, breadcrumb_graph, dumps_jsonld

    # Drafts and scheduled articles 404 for visitors and stay readable for
    # staff, so an article can be checked in place before it goes live.
    visible = Article.objects.all() if request.user.is_staff else published_articles()
    article = get_object_or_404(visible, slug=slug)

    # A staff preview of a draft or a scheduled article must not leak into
    # an index or a rich result: noindex in the template, no Article JSON-LD.
    is_preview = not article.is_public

    crumbs = [
        ("Головна", "/"),
        ("Блог", reverse("blog")),
        (article.title, article.get_absolute_url()),
    ]
    return render(
        request,
        "blog_inside.html",
        context={
            "article": article,
            "is_preview": is_preview,
            "related": related_articles(article),
            "catalog_cta_url": catalog_cta_url(article),
            "article_jsonld": (
                "" if is_preview else dumps_jsonld(article_graph(request, article))
            ),
            "breadcrumb_jsonld": dumps_jsonld(breadcrumb_graph(request, crumbs)),
        },
    )
