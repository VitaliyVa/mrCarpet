from django.contrib import admin
from .models import Article


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    exclude = ['slug']
    list_display = ['title', 'created', 'updated']
    search_fields = ['title', 'meta_title']
    fieldsets = (
        ('Основне', {
            'fields': ('title', 'description', 'image'),
        }),
        ('SEO', {
            'fields': ('meta_title', 'meta_description', 'meta_keys'),
            'description': (
                'Мета-теги статті. Якщо порожньо — fallback з назви/тексту статті.'
            ),
        }),
    )
