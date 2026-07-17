from celery import shared_task


@shared_task(bind=True, max_retries=1, soft_time_limit=300, time_limit=360)
def generate_ar_texture_task(self, product_id: int):
    from catalog.models import Product
    from catalog.services.ar_texture import ArTextureService
    from catalog.services.replicate_product_images import ReplicateGenerationError

    try:
        product = Product.admin_objects.get(pk=product_id)
    except Product.DoesNotExist:
        return {"success": False, "error": f"Product {product_id} not found"}

    try:
        return ArTextureService().generate_for_product(product)
    except ReplicateGenerationError as exc:
        return {"success": False, "product_id": product_id, "error": str(exc)}
    except Exception as exc:
        return {"success": False, "product_id": product_id, "error": str(exc)}


@shared_task(bind=True, max_retries=0, soft_time_limit=3600, time_limit=3900)
def generate_seo_batch_task(self, product_ids: list[int]):
    """One task, sequential loop — never fan-out N parallel Replicate calls."""
    from catalog.services.seo_generate import generate_seo_for_products

    return generate_seo_for_products(list(product_ids or []))
