from django.shortcuts import render, get_object_or_404
from .models import Article

# Create your views here.
def blog(request):
    articles = Article.objects.all()[::-1]
    return render(request, 'blog.html', context={'articles': articles})

def post(request, slug):
    from django.urls import reverse

    from project.seo_jsonld import article_graph, breadcrumb_graph, dumps_jsonld

    article = get_object_or_404(Article, slug=slug)
    articles = Article.objects.exclude(slug=slug)[::-1]
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
            "articles": articles,
            "article_jsonld": dumps_jsonld(article_graph(request, article)),
            "breadcrumb_jsonld": dumps_jsonld(breadcrumb_graph(request, crumbs)),
        },
    )