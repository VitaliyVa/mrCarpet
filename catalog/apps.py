from django.apps import AppConfig


class CatalogConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'catalog'

    def ready(self):
        from django.db.models.signals import post_delete, post_save

        from .models import ProductAttribute, ProductSale
        from .promotions import clear_promo_cache

        # The header's «Акції» link is cached (catalog/promotions.py); a saved
        # discount or quantity shows up in this process at once.
        for model in (ProductAttribute, ProductSale):
            post_save.connect(clear_promo_cache, sender=model, dispatch_uid=f"promo-save-{model.__name__}")
            post_delete.connect(clear_promo_cache, sender=model, dispatch_uid=f"promo-del-{model.__name__}")
