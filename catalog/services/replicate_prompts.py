PROMPT_VERSION = "2"

_ASPECT_NOTE = (
    "Output must be a vertical 2:3 portrait image. "
    "The rug must completely fill the 2:3 canvas with zero margins."
)

_NO_WHITESPACE = """
CRITICAL FRAMING — NO EMPTY SPACE:
- The rug must extend to every edge of the image: the left edge of the rug touches the left edge of the image, the right edge of the rug touches the right edge of the image, the top edge of the rug touches the top edge of the image, the bottom edge of the rug touches the bottom edge of the image.
- Absolutely NO white background, NO grey background, NO floor, NO padding, NO letterboxing, NO pillarboxing, NO empty margins, NO borders, NO vignette outside the rug.
- If the reference has white or empty space around the rug, REMOVE it and reframe so only the rug fills the entire image.
- The image must be cropped exactly at the rug perimeter — where the rug ends, the image ends.
- The rug occupies 100% of the image area; every pixel is rug surface or rug edge binding."""

_PRESERVATION = """
STRICT PRESERVATION (do NOT change):
- Preserve the exact original pattern, motif layout, colors, color distribution, proportions, texture, pile direction, and material appearance.
- Do not redesign, simplify, stylize, recolor, warp, stretch, or reinterpret the rug design in any way.
- The rug must look identical to the reference — only camera angle, framing, and presentation change."""

PROMPT_CATALOG_IMAGE = f"""Edit the provided reference image of a rug/carpet for an e-commerce catalog thumbnail.

CAMERA & COMPOSITION (change only this):
- Perfect top-down orthogonal view: camera directly above the rug at 90 degrees, zero perspective distortion, no rotation, no tilt, no 3D angle.
- The entire rug must be fully visible — all four edges visible and aligned with the image borders.
- {_ASPECT_NOTE}
{_NO_WHITESPACE}
- Center the rug symmetrically in the vertical 2:3 frame.

{_PRESERVATION}

OUTPUT:
- Clean professional product catalog photography, even soft lighting, sharp focus across the whole rug surface."""

PROMPT_HOVER_IMAGE = f"""Edit the provided reference image of a rug/carpet into a premium macro product detail shot for an e-commerce hover state.

CAMERA & COMPOSITION (change only this):
- Move closer to the rug: macro / close-up product photography in vertical 2:3 portrait format.
- Show a natural diagonal fold or curl of one corner/edge lifted toward the camera, revealing the rug's thickness, edge binding/overlock stitching, and pile texture — similar to a tactile lifestyle detail shot.
- Use shallow depth of field: the folded edge and nearby pile fibers in the foreground are tack-sharp; the rest of the rug surface behind the fold is softly blurred with smooth creamy bokeh.
- Keep the same rug pattern visible in both sharp and blurred areas.
- {_ASPECT_NOTE}
- The visible rug area must fill the frame edge-to-edge with no white margins or empty space outside the rug.

{_PRESERVATION}

LIGHTING & STYLE:
- Soft directional studio lighting from the side, subtle shadows in the fold, premium tactile feel.
- Photorealistic, no text, no watermark, no props, no people."""
