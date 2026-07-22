"""Catalog admin package.

Split out of a single 1400-line module for navigability. Importing the
submodules here runs every ``admin.site.register(...)`` exactly as the old flat
module did, and re-exports the admin classes so ``from catalog.admin import X``
keeps working.
"""

from .widgets import ColorSelectWidget, ImagePreviewWidget
from .inlines import (
    FavouriteItemInLine,
    ProductImageInline,
    ProductInLine,
    RelatedProductInline,
    SpecificationInline,
)
from .product import ProductAdmin
from .misc import (
    ColorGroupAdmin,
    FavouriteAdmin,
    ProductCategoryAdmin,
    ProductColorAdmin,
    ProductReviewAdmin,
    PromoCodeAdmin,
    SizeAdmin,
    SpecificationValueAdmin,
)

__all__ = [
    "ColorSelectWidget",
    "ImagePreviewWidget",
    "FavouriteItemInLine",
    "ProductImageInline",
    "ProductInLine",
    "RelatedProductInline",
    "SpecificationInline",
    "ProductAdmin",
    "ColorGroupAdmin",
    "FavouriteAdmin",
    "ProductCategoryAdmin",
    "ProductColorAdmin",
    "ProductReviewAdmin",
    "PromoCodeAdmin",
    "SizeAdmin",
    "SpecificationValueAdmin",
]
