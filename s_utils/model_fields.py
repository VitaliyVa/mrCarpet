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
    origin_value = slugify(unidecode(instance.title))
    generated_slug = check_s_availability(instance, origin_value)
    return generated_slug