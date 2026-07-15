"""Match generated rug colors to the source photo (catalog pipeline)."""
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


def _rug_mask_from_output(img: Image.Image) -> Image.Image:
    """Rug silhouette on catalog output — does not change between before/after color fix."""
    gray = img.convert('L')
    mask = gray.point(lambda p: 255 if p < 245 else 0)
    if ImageStat.Stat(mask).sum[0] > img.size[0] * img.size[1] * 0.15 * 255:
        return mask
    return _ellipse_mask_image(img.size, inset=0.04)


def _masked_luminance_stats(img: Image.Image, mask: Image.Image) -> tuple[float, float]:
    lum = img.convert('L')
    masked = ImageChops.multiply(lum, mask)
    stat = ImageStat.Stat(masked, mask)
    mean = float(stat.mean[0])
    std = float(stat.stddev[0]) if hasattr(stat, 'stddev') else 40.0
    return mean, max(std, 10.0)


def match_rug_colors(source_bytes: bytes, generated_bytes: bytes) -> bytes:
    """
    Adjust brightness/contrast of generated rug to match source reference.

    Shape is never touched — only pixel values inside the existing rug mask change.
    Uses a single luminance scale+offset applied equally to R/G/B (neutral grays stay neutral).
    If the model washed out the rug (lighter mean), apply an extra darkening bias.
    """
    source = Image.open(io.BytesIO(source_bytes)).convert('RGB')
    generated = Image.open(io.BytesIO(generated_bytes)).convert('RGB')

    if source.size != generated.size:
        source = source.resize(generated.size, Image.Resampling.LANCZOS)

    work_w = min(512, generated.size[0])
    work_h = max(1, round(generated.size[1] * work_w / generated.size[0]))
    src_work = source.resize((work_w, work_h), Image.Resampling.LANCZOS)
    gen_work = generated.resize((work_w, work_h), Image.Resampling.LANCZOS)

    # Tighter ellipse on source = pile field, less floor bleed at edges.
    src_mask = _ellipse_mask_image(src_work.size, inset=0.14)
    gen_mask = _rug_mask_from_output(gen_work)

    src_mean, src_std = _masked_luminance_stats(src_work, src_mask)
    gen_mean, gen_std = _masked_luminance_stats(gen_work, gen_mask)

    target_mean = src_mean - 14.0
    target_std = src_std * 1.35
    if gen_mean > src_mean:
        target_mean -= min(10.0, (gen_mean - src_mean) * 0.5)

    scale = target_std / gen_std
    offset = target_mean - gen_mean * scale

    rug_mask = _rug_mask_from_output(generated)
    r, g, b = generated.split()

    def adjust(band: Image.Image) -> Image.Image:
        return band.point(lambda p: max(0, min(255, int(p * scale + offset))))

    corrected = Image.merge('RGB', (adjust(r), adjust(g), adjust(b)))
    result = Image.composite(corrected, generated, rug_mask)

    buf = io.BytesIO()
    result.save(buf, format='WEBP', quality=92, method=6)
    return buf.getvalue()
