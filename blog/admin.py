from django.contrib import admin
from django.http import JsonResponse
from django.urls import path
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST

from .models import Article


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    exclude = ["slug"]
    list_display = ["title", "created", "updated"]
    search_fields = ["title", "meta_title"]
    fieldsets = (
        (
            "Основне",
            {
                "fields": ("title", "description", "image"),
                "description": (
                    "На <b>списку</b> статей є кнопка "
                    "«Згенерувати пост (Replicate)»: тема → "
                    "2× текст (gpt-4o-mini: каркас + розгортання) + "
                    "обкладинка (gpt-image-2, quality=low). "
                    "Після генерації відкриється форма для ручних правок. "
                    "~1–2 хв, не закривайте вкладку."
                ),
            },
        ),
        (
            "SEO",
            {
                "fields": ("meta_title", "meta_description", "meta_keys"),
                "description": (
                    "Мета-теги статті. Якщо порожньо — fallback з назви/тексту статті."
                ),
            },
        ),
    )

    class Media:
        js = ("admin/js/replicate_generate_article.js",)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "generate-article/",
                self.admin_site.admin_view(self.generate_article),
                name="blog_article_generate",
            ),
        ]
        return custom + urls

    @method_decorator(require_POST)
    def generate_article(self, request):
        from blog.services.article_generate import (
            ArticleGenerationError,
            ReplicateArticleService,
        )

        topic = (request.POST.get("topic") or "").strip()
        try:
            result = ReplicateArticleService().generate_and_create(topic)
        except ArticleGenerationError as exc:
            return JsonResponse({"success": False, "error": str(exc)}, status=400)
        except Exception:
            import logging

            logging.getLogger("blog.article_generate").exception(
                "Article generate failed"
            )
            return JsonResponse(
                {
                    "success": False,
                    "error": "Несподівана помилка генерації. Перевірте логи сервера.",
                },
                status=500,
            )

        return JsonResponse(
            {
                "success": True,
                "article_id": result.article_id,
                "title": result.title,
                "edit_url": result.edit_url,
                "text_duration_sec": result.text_duration_sec,
                "image_duration_sec": result.image_duration_sec,
                "models": result.models,
            }
        )
