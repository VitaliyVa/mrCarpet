from django.shortcuts import render
from .models import Article

# Create your views here.
def blog(request):
    articles = Article.objects.all()
    return render(request, 'blog.html', context={'articles': articles})