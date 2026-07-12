import io

from PIL import Image


def optimize_product_image(data: bytes, max_width: int = 500, quality: int = 90) -> bytes:
    """Mirror of static/admin/js/image_resize.js for image/hover_image fields."""
    img = Image.open(io.BytesIO(data))
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    elif img.mode == "RGBA":
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        img = background

    width, height = img.size
    if width > max_width:
        height = max(1, round(height * max_width / width))
        width = max_width
        img = img.resize((width, height), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=quality, method=6)
    return buf.getvalue()
