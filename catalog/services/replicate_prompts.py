from catalog.services.replicate_prompt_options import CatalogPromptOptions, ScenePromptOptions

PROMPT_VERSION = "4"

_ASPECT_NOTE = (
    "Output must be a vertical 2:3 portrait image. "
    "The rug must completely fill the 2:3 canvas with zero margins outside the rug silhouette."
)

_NO_WHITESPACE = """
CRITICAL FRAMING — NO EMPTY SPACE:
- Crop tightly to the rug's exact perimeter/silhouette. Where the rug ends, the image ends.
- Absolutely NO white background, NO floor, NO room, NO padding, NO letterboxing, NO empty margins.
- If the reference shows floor, walls, or room around the rug, REMOVE them completely.
- The rug silhouette must touch the image borders on all sides (top, bottom, left, right) with zero gap."""

_PRESERVATION = """
STRICT PRESERVATION (do NOT change):
- Preserve the exact original pattern, motif layout, colors, color distribution, texture, pile direction, and material appearance.
- Do not redesign, simplify, stylize, recolor, warp, stretch, or reinterpret the rug design.
- The rug must look identical to the reference — only camera angle, isolation, and framing change."""

_SHAPE_BLOCKS = {
    'auto': """
RUG SHAPE (CRITICAL):
- Preserve the EXACT silhouette and outline from the reference — oval, round, rectangular, runner, or irregular.
- Do NOT regularize the shape: never convert oval to rectangle, never square off curved edges, never change proportions.
- Match the reference perimeter precisely, including curved vs straight edges and corner style.""",
    'oval': """
RUG SHAPE (CRITICAL — OVAL):
- The rug MUST stay OVAL / elliptical (stadium shape): two long curved sides and two curved ends.
- NO straight long sides, NO 90-degree corners, NO rectangle, NO rounded-rectangle, NO square.
- Preserve the exact oval proportions and curved perimeter from the reference. Do not rectangularize.""",
    'rectangular': """
RUG SHAPE (CRITICAL — RECTANGULAR):
- The rug MUST stay rectangular with the same corner style as the reference (sharp or slightly rounded corners).
- Preserve exact length-to-width ratio. Do not convert to oval or round.""",
    'round': """
RUG SHAPE (CRITICAL — ROUND):
- The rug MUST stay circular / round. Preserve the exact circle diameter and outline from the reference.
- Do not convert to oval or rectangle.""",
    'runner': """
RUG SHAPE (CRITICAL — RUNNER):
- The rug MUST stay a long narrow runner (rectangular strip). Preserve exact length-to-width ratio from the reference.
- Do not convert to square, oval, or standard area rug proportions.""",
}

_SOURCE_BLOCKS = {
    'auto': """
SOURCE PHOTO:
- If the reference shows the rug on a floor or in a room, isolate ONLY the rug and remove all floorboards, tiles, furniture, and surroundings.""",
    'in_room': """
SOURCE PHOTO (in-room):
- The reference is a room/floor photo. Extract ONLY the rug — remove wooden floor, tiles, shadows of the room, and all background.
- Re-frame as a clean catalog product shot of the rug alone.""",
    'isolated': """
SOURCE PHOTO (isolated):
- The reference is already an isolated rug photo. Keep a clean tight crop to the rug edge without adding floor or background.""",
}

_COLOR_BLOCKS = {
    'auto': """
COLOR:
- Preserve the exact colors and tonal balance from the reference.""",
    'preserve_exact': """
COLOR:
- Preserve pixel-accurate colors, contrast, and tonal distribution from the reference. No recoloring or color grading.""",
    'monochrome': """
COLOR:
- This is a monochrome / grayscale rug. Preserve the exact gray, charcoal, silver, and black tones from the reference without adding color.""",
}


def build_catalog_prompt(options: CatalogPromptOptions | None = None) -> str:
    opts = (options or CatalogPromptOptions()).normalized()

    return f"""Edit the provided reference image of a rug/carpet for an e-commerce catalog thumbnail.

CAMERA & COMPOSITION (change only this):
- Perfect top-down orthogonal view: camera directly above at 90 degrees, zero perspective, no tilt, no 3D angle.
- Show the entire rug fully inside the frame; crop to the rug silhouette only.
- {_ASPECT_NOTE}
{_NO_WHITESPACE}
- Center the rug in the vertical 2:3 frame.

{_SHAPE_BLOCKS[opts.rug_shape]}
{_SOURCE_BLOCKS[opts.source_context]}
{_COLOR_BLOCKS[opts.color_mode]}

{_PRESERVATION}

OUTPUT:
- Clean professional catalog product photography, even soft lighting, sharp focus across the whole rug surface."""


def build_hover_prompt(options: CatalogPromptOptions | None = None) -> str:
    opts = (options or CatalogPromptOptions()).normalized()
    shape_hint = _SHAPE_BLOCKS[opts.rug_shape]

    return f"""Edit the provided reference image of a rug/carpet into a premium macro product detail shot for an e-commerce hover state.

CAMERA & COMPOSITION (change only this):
- Move closer: macro / close-up product photography in vertical 2:3 portrait format.
- Show a natural diagonal fold or curl of one edge lifted toward the camera, revealing thickness, edge binding/stitching, and pile texture.
- Shallow depth of field: folded edge tack-sharp; background area softly blurred with creamy bokeh.
- {_ASPECT_NOTE}
- Visible rug area fills the frame edge-to-edge.

{shape_hint}
{_COLOR_BLOCKS[opts.color_mode]}

{_PRESERVATION}

LIGHTING & STYLE:
- Soft directional studio lighting, premium tactile feel. Photorealistic, no text, no watermark."""


_ROOM_BLOCKS = {
    'auto': """
ROOM:
- Place the rug in a tasteful, photorealistic modern interior that complements the rug's style and colors.
- Neutral contemporary decor, natural daylight, believable furniture placement.""",
    'living_room': """
ROOM (living room):
- Cozy modern living room: sofa, coffee table, soft textiles, warm natural daylight from a window.
- The rug lies on the floor as the focal point of the seating area.""",
    'bedroom': """
ROOM (bedroom):
- Calm, elegant bedroom with bed, bedside tables, neutral linens, soft morning light.
- The rug is placed beside or under the bed area on the floor.""",
    'kids_room': """
ROOM (kids/playroom):
- Bright, friendly children's room or playroom with safe, cheerful decor (no brand logos).
- The rug is on the floor as a play area centerpiece.""",
    'dining_room': """
ROOM (dining room):
- Dining area with table, chairs, subtle decor, balanced natural and ambient light.
- The rug is under or beside the dining table on the floor.""",
    'hallway': """
ROOM (hallway/entryway):
- Clean entryway or hallway with minimal furniture, mirror or console optional, bright and welcoming.
- The rug lies on the floor in the passage area.""",
    'office': """
ROOM (home office):
- Minimal home office with desk, chair, tidy shelves, soft daylight.
- The rug is on the floor under or near the desk area.""",
}

_DISTANCE_BLOCKS = {
    'close': """
CAMERA DISTANCE (close):
- Close lifestyle shot: the rug dominates the frame (roughly 70–85% visible area).
- Show pile texture and pattern clearly; only partial furniture/legs at frame edges.""",
    'medium': """
CAMERA DISTANCE (medium):
- Standard interior lifestyle shot: rug clearly visible on the floor (~45–60% of frame).
- Balanced view of rug plus surrounding furniture and room context.""",
    'wide': """
CAMERA DISTANCE (wide):
- Wide room establishing shot: full room context with rug visible on the floor (~25–40% of frame).
- Show how the rug fits the space; more walls and furniture visible.""",
}

_VIEW_BLOCKS = {
    'eye_level': """
CAMERA ANGLE:
- Natural eye-level interior photography (~100–130 cm height), gentle realistic perspective.
- Not flat orthographic — believable room depth.""",
    'high_angle': """
CAMERA ANGLE:
- Elevated angle (~30–45°) looking down toward the rug and floor, showing more rug surface.
- Still a room scene, not a flat catalog cutout.""",
    'top_down_partial': """
CAMERA ANGLE:
- Higher near-top-down angle emphasizing rug surface and pattern while keeping minimal room cues at edges.
- More rug, less wall — but still an in-room scene, not isolated on white.""",
}

_FLOOR_BLOCKS = {
    'auto': """
FLOOR:
- Choose a floor material that complements the rug (wood, tile, or laminate) with realistic texture.""",
    'wood': """
FLOOR:
- Dark or medium hardwood floorboards with natural grain, matte finish.""",
    'light_wood': """
FLOOR:
- Light oak or birch wood floor with visible grain, Scandinavian feel.""",
    'tile': """
FLOOR:
- Large-format neutral ceramic or stone tiles, subtle texture, clean grout lines.""",
    'concrete': """
FLOOR:
- Polished or matte concrete floor, modern minimal look.""",
}


def build_scene_prompt(options: ScenePromptOptions | None = None) -> str:
    opts = (options or ScenePromptOptions()).normalized()

    return f"""Edit the provided reference image of a rug/carpet into a photorealistic in-room lifestyle product photo for an e-commerce product page gallery.

GOAL:
- Place THIS EXACT rug (same pattern, colors, texture) naturally on the floor in a real interior scene.
- Output a horizontal 4:3 landscape image suitable for a product page slider.

{_SHAPE_BLOCKS[opts.rug_shape]}
{_COLOR_BLOCKS[opts.color_mode]}

{_ROOM_BLOCKS[opts.room_type]}
{_FLOOR_BLOCKS[opts.floor_style]}
{_DISTANCE_BLOCKS[opts.camera_distance]}
{_VIEW_BLOCKS[opts.view_angle]}

STRICT PRESERVATION (do NOT change the rug):
- The rug pattern, motif layout, colors, texture, pile, and material must match the reference exactly.
- Do not redesign, recolor, simplify, or substitute a different rug.
- Preserve the rug's exact shape silhouette on the floor (oval stays oval, rectangular stays rectangular).

SCENE RULES:
- Photorealistic interior photography, soft natural daylight, no text, no watermark, no people.
- Furniture and decor should feel premium and contemporary; do not overpower the rug.
- The rug must sit flat on the floor with realistic contact shadows and scale."""
