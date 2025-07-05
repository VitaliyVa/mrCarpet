from unidecode import unidecode
from django.utils.text import slugify


# def generate_slug(instance):
#     origin_value = instance.slug
#     if origin_value is None:
#         origin_value = slugify(unidecode(instance.title))
#         new_slug = origin_value
#         num = 1
#         while instance._meta.model.objects.filter(slug=new_slug).exclude(id=instance.id).exists():
#             new_slug = f"{origin_value}-{num}"
#             num += 1
#         return new_slug
#     return origin_value

def check_s_availability(instance, origin_value):
    new_slug = origin_value
    num = 1
    while instance._meta.model.objects.filter(slug=new_slug).exclude(id=instance.id).exists():
        new_slug = f"{origin_value}-{num}"
        num += 1
    return new_slug

def generate_slug(instance):
    # Перевіряємо чи title не є None або порожнім
    if not instance.title or instance.title.strip() == '':
        # Якщо title порожній, генеруємо slug на основі ID або інших полів
        if hasattr(instance, 'color') and instance.color:
            # Для ProductColor використовуємо hex код кольору
            origin_value = slugify(str(instance.color).replace('#', 'color-'))
        else:
            # Для інших моделей використовуємо назву моделі + timestamp
            import time
            origin_value = slugify(f"{instance._meta.model_name}-{int(time.time())}")
    else:
        origin_value = slugify(unidecode(instance.title))
    
    generated_slug = check_s_availability(instance, origin_value)
    return generated_slug