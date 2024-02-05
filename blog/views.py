from django.shortcuts import render, get_object_or_404
from .models import Article

# Create your views here.
def blog(request):
    articles = Article.objects.all()[::-1]
    return render(request, 'blog.html', context={'articles': articles})

def post(request, slug):
    article = get_object_or_404(Article, slug=slug)
    articles = Article.objects.exclude(slug=slug)[::-1]
    return render(request, 'blog_inside.html', context={'article': article, 'articles': articles})