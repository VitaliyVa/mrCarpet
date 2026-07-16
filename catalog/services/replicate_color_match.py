"""Match generated rug colors/lighting to the source photo (catalog pipeline)."""
from __future__ import annotations

import io

from PIL import Image, ImageChops, ImageDraw, ImageStat


def _ellipse_mask_image(size: tuple[int, int], inset: float = 0.08) -> Image.Image:
    w, h = size
    mask = Image.new('L', (w, h), 0)
    draw = ImageDraw.Draw(mask)
    pad_x = int(w * inset)
    pad_y = int(h * inset)
    draw.ellipse((pad_x, pad_y, w - pad_x, h - pad_y), fill=255)
    return mask


def _center_mask_image(size: tuple[int, int], inset: float = 0.12) -> Image.Image:
    """Rectangular center mask — works for oval, semicircle, rectangular rugs."""
    w, h = size
    mask = Image.new('L', (w, h), 0)
    draw = ImageDraw.Draw(mask)
    pad_x = int(w * inset)
    pad_y = int(h * inset)
    draw.rectangle((pad_x, pad_y, w - pad_x, h - pad_y), fill=255)
    return mask


def _rug_mask_from_output(img: Image.Image) -> Image.Image:
    """Rug silhouette on catalog output — does not change between before/after color fix."""
    gray = img.convert('L')
    mask = gray.point(lambda p: 255 if p < 245 else 0)
    if ImageStat.Stat(mask).sum[0] > img.size[0] * img.size[1] * 0.15 * 255:
        return mask
    return _ellipse_mask_image(img.size, inset=0.04)


def _masked_channel_stats(band: Image.Image, mask: Image.Image) -> tuple[float, float]:
    masked = ImageChops.multiply(band, mask)
    stat = ImageStat.Stat(masked, mask)
    mean = float(stat.mean[0])
    std = float(stat.stddev[0]) if hasattr(stat, 'stddev') else 40.0
    return mean, max(std, 8.0)


def match_rug_colors(source_bytes: bytes, generated_bytes: bytes) -> bytes:
    """
    Match generated rug brightness, contrast, and saturation to the source photo.

    Faithful match only — no darkening bias, no contrast boost (those made colors
    look artificially punchy / brighter than the real product).
    Shape is never touched.
    """
    source = Image.open(io.BytesIO(source_bytes)).convert('RGB')
    generated = Image.open(io.BytesIO(generated_bytes)).convert('RGB')

    if source.size != generated.size:
        source = source.resize(generated.size, Image.Resampling.LANCZOS)

    work_w = min(512, generated.size[0])
    work_h = max(1, round(generated.size[1] * work_w / generated.size[0]))
    src_work = source.resize((work_w, work_h), Image.Resampling.LANCZOS)
    gen_work = generated.resize((work_w, work_h), Image.Resampling.LANCZOS)

    # Center sample on source avoids bright floor around the rug.
    src_mask = _center_mask_image(src_work.size, inset=0.16)
    gen_mask = _rug_mask_from_output(gen_work)

    src_lum = src_work.convert('L')
    gen_lum = gen_work.convert('L')
    src_mean, src_std = _masked_channel_stats(src_lum, src_mask)
    gen_mean, gen_std = _masked_channel_stats(gen_lum, gen_mask)

    # Exact tonal match to source — never push darker/punchier than the photo.
    scale = src_std / gen_std
    # Cap contrast stretch so we don't invent punchy contrast.
    scale = min(scale, 1.08)
    offset = src_mean - gen_mean * scale

    rug_mask = _rug_mask_from_output(generated)
    r, g, b = generated.split()

    def adjust_lum(band: Image.Image) -> Image.Image:
        return band.point(lambda p: max(0, min(255, int(p * scale + offset))))

    corrected = Image.merge('RGB', (adjust_lum(r), adjust_lum(g), adjust_lum(b)))

    # Pull saturation down if the model oversaturated vs source.
    src_s = src_work.convert('HSV').split()[1]
    gen_s = gen_work.convert('HSV').split()[1]
    src_s_mean, _ = _masked_channel_stats(src_s, src_mask)
    gen_s_mean, _ = _masked_channel_stats(gen_s, gen_mask)

    if gen_s_mean > src_s_mean + 2 and gen_s_mean > 1:
        sat_scale = max(0.55, min(1.0, src_s_mean / gen_s_mean))
        h, s, v = corrected.convert('HSV').split()
        s = s.point(lambda p: max(0, min(255, int(p * sat_scale))))
        corrected = Image.merge('HSV', (h, s, v)).convert('RGB')

    result = Image.composite(corrected, generated, rug_mask)

    buf = io.BytesIO()
    result.save(buf, format='WEBP', quality=92, method=6)
    return buf.getvalue()


def crop_white_margins(image_bytes: bytes, threshold: int = 245, pad: int = 2) -> bytes:
    """
    Crop uniform white padding around the rug bbox.

    Keeps white only inside the bbox corners (curve wedges).
    Shape is not changed — only outer empty margins are removed.
    """
    img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    gray = img.convert('L')
    mask = gray.point(lambda p: 255 if p < threshold else 0)
    bbox = mask.getbbox()
    if not bbox:
        return image_bytes

    x0, y0, x1, y1 = bbox
    x0 = max(0, x0 - pad)
    y0 = max(0, y0 - pad)
    x1 = min(img.size[0], x1 + pad)
    y1 = min(img.size[1], y1 + pad)
    cropped = img.crop((x0, y0, x1, y1))

    buf = io.BytesIO()
    cropped.save(buf, format='WEBP', quality=92, method=6)
    return buf.getvalue()
