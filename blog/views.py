from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.shortcuts import get_object_or_404, render

from .models import Article

#: Articles per page. The list used to fetch every row and reverse it in
#: Python — fine at ten posts, a full table scan at a hundred.
PER_PAGE = 9


def published_articles():
    """
    The only queryset the public side may use.

    Ordering comes from Meta, so it happens in SQL rather than by slicing the
    whole table backwards in memory.
    """
    return Article.objects.filter(status=Article.Status.PUBLISHED)


def blog(request):
    from django.urls import reverse

    from project.seo_jsonld import breadcrumb_graph, dumps_jsonld

    paginator = Paginator(published_articles(), PER_PAGE)
    page = request.GET.get("page")
    try:
        articles = paginator.page(page)
    except PageNotAnInteger:
        articles = paginator.page(1)
    except EmptyPage:
        articles = paginator.page(paginator.num_pages)

    crumbs = [("Головна", "/"), ("Блог", reverse("blog"))]
    return render(
        request,
        "blog.html",
        context={
            "articles": articles,
            "page_obj": articles,
            "paginator": paginator,
            # The detail page carried breadcrumbs in JSON-LD while the list
            # drew them only as HTML, so the trail Google saw stopped one
            # level short of the reader's.
            "breadcrumb_jsonld": dumps_jsonld(breadcrumb_graph(request, crumbs)),
        },
    )


def post(request, slug):
    from django.urls import reverse

    from project.seo_jsonld import article_graph, breadcrumb_graph, dumps_jsonld

    # Drafts 404 for visitors and stay readable for staff, so an article can
    # be checked in place before it goes live.
    visible = Article.objects.all() if request.user.is_staff else published_articles()
    article = get_object_or_404(visible, slug=slug)

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
            "articles": published_articles().exclude(pk=article.pk)[:6],
            "article_jsonld": dumps_jsonld(article_graph(request, article)),
            "breadcrumb_jsonld": dumps_jsonld(breadcrumb_graph(request, crumbs)),
        },
    )
