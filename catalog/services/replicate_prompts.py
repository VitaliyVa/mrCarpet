from catalog.services.replicate_prompt_options import CatalogPromptOptions, ScenePromptOptions

PROMPT_VERSION = "14"

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

# Oval cannot touch all 4 borders without distorting shape — allow side margins.
_OVAL_ASPECT_NOTE = (
    "Output must be a vertical 2:3 portrait image. "
    "Center a bilaterally symmetric vertical oval. Crop tightly to the rug bbox — "
    "minimal outer white padding; side white only in the oval corner wedges."
)

_OVAL_FRAMING = """
CRITICAL — PERSPECTIVE DESKEW (REFERENCE IS TILTED):
- The source photo is NOT orthographic: camera tilt makes the NEAR end look longer/sharper and the FAR end flatter/wider.
- You MUST fully remove that foreshortening. Output a perfect 90° top-down / orthographic oval.
- After correction, if you flip the rug upside-down, the silhouette must look the SAME (180° rotational symmetry of the outline).
- Top end and bottom end MUST match: same chord width, same curve radius, same roundness.
- FORBIDDEN silhouettes copied from tilted photos: egg shape, teardrop, pointier bottom, wider bottom, flatter top, trapezoid oval.
- If the reference bottom looks sharper/longer than the top — ROUND AND SHORTEN the bottom to match the top (and vice versa). Do NOT keep the asymmetry.
- Isolate ONLY the rug on solid white (#FFFFFF). Remove floor, wood, room, shadows.
- Ends: broad, soft, gently rounded — NOT pointed tips. Continuous smooth curve. NO 90-degree corners."""

_REMOVE_HANGTAG = """
REMOVE HANG TAG / HANGER (CRITICAL — IF PRESENT ON THE REFERENCE):
- Retail photos often have a plastic hanger, metal hook, cardboard brand card, price sticker, barcode, or clip attached to the rug edge (usually top center), with text/price/brand photos.
- These are NOT part of the product. Completely remove the hanger, hook, cardboard label, price tag, clips, strings, and any shadow they cast.
- Reconstruct the occluded rug area underneath: continue the border binding and the weave/pattern from the surrounding visible rug so the patch is seamless.
- Match adjacent color, texture, pile direction, and motif — do not invent a new design, leave a blank/white hole, blur blob, or ghost outline of the label.
- Final rug must look clean as if no hang tag was ever attached."""

_PRESERVATION = """
STRICT PRESERVATION (do NOT change):
- Preserve the exact original pattern, motif layout, colors, color distribution, texture, pile direction, and material appearance.
- Do not redesign, simplify, stylize, recolor, warp, stretch, or reinterpret the rug design.
- The rug must look identical to the reference — only camera angle, isolation, framing, and hang-tag removal/inpaint change.
- Hang tags/hangers/price cards are packaging props — remove them and restore the rug underneath."""

_OVAL_PRESERVATION = """
STRICT PRESERVATION (pattern/colors only — silhouette MAY be corrected):
- Preserve the exact original pattern, motif layout, colors, color distribution, texture, pile direction, and material appearance.
- Do not redesign, simplify, stylize, recolor, or reinterpret the rug design.
- You MAY and MUST correct camera perspective / silhouette asymmetry (tilted oval → symmetric top-down oval).
- Do NOT copy the reference's egg-shaped or foreshortened outline — that outline is a photography artifact.
- Hang tags/hangers/price cards are packaging props — remove them and restore the rug underneath."""

_SEMICIRCLE_ASPECT_NOTE = (
    "Output must be a vertical 2:3 portrait image. "
    "Center a true SEMICIRCLE (half-disk / D-shape). Crop tightly to the rug bbox — "
    "minimal outer white padding; white only outside the semicircle silhouette."
)

_SEMICIRCLE_FRAMING = """
CRITICAL — SEMICIRCLE / HALF-DISK (DESKEWED):
- Isolate ONLY the rug on solid white (#FFFFFF). Remove floor, wood, room, shadows, labels, and tags.
- Silhouette = exact mathematical semicircle: ONE perfectly STRAIGHT diameter edge + ONE continuous 180° circular arc of CONSTANT radius.
- Keep the diameter orientation from the reference (straight edge on the same side as in the photo).
- The arc MUST be a true half-circle — not a flatter bow, not a deeper U, not an oval half, not a quarter-circle.
- Where the arc meets the diameter: clean right-angle junctions of geometry (curve meets straight ends), no chopped corners.
- Reference may be tilted — CORRECT to perfect 90° top-down orthographic view. No perspective taper.
- FORBIDDEN: full circle, oval, rectangle with one rounded side, irregular D-shape, asymmetric arc."""

_SEMICIRCLE_PRESERVATION = """
STRICT PRESERVATION (pattern/colors only — silhouette MAY be corrected):
- Preserve the exact original pattern, motif layout, colors, color distribution, texture, pile direction, and material appearance.
- Do not redesign, simplify, stylize, recolor, or reinterpret the rug design.
- You MAY and MUST correct camera perspective so the outline becomes a true geometric semicircle.
- Do NOT copy foreshortened / skewed outline from the angled photo.
- Hang tags/hangers/price cards are packaging props — remove them and restore the rug underneath."""

# Circle in a tall 2:3 frame gets side-clipped if forced to "touch left/right" — use square canvas + safe margins.
_ROUND_ASPECT_NOTE = (
    "Output must be a square 1:1 image. "
    "Center a perfect CIRCLE rug with a small equal white margin on ALL four sides "
    "(about 2–4% of the canvas). The full circumference must stay inside the frame."
)

_ROUND_FRAMING = """
CRITICAL FRAMING — FULL CIRCLE, NEVER CLIP SIDES:
- Isolate ONLY the rug on solid white (#FFFFFF). Remove floor, room, shadows, labels.
- Silhouette = perfect mathematical circle, constant radius, top-down orthographic.
- The WHOLE circle must be visible: left and right edges must NOT touch or cross the frame borders.
- Keep a thin equal white gap around the entire circumference — never crop/cut the left or right arc.
- FORBIDDEN: oval, truncated circle, circle touching left/right borders, side clipping, squashed ellipse."""

_ROUND_PRESERVATION = """
STRICT PRESERVATION (pattern/colors only — silhouette MAY be corrected):
- Preserve the exact original pattern, motif layout, colors, color distribution, texture, pile direction, and material appearance.
- Do not redesign, simplify, stylize, recolor, or reinterpret the rug design.
- You MAY correct camera perspective so the outline becomes a perfect circle.
- Do NOT clip the circle to fit the frame — scale the whole rug down so it fits with margin.
- Hang tags/hangers/price cards are packaging props — remove them and restore the rug underneath."""

_SHAPE_BLOCKS = {
    'auto': """
RUG SHAPE (CRITICAL):
- Preserve the EXACT silhouette and outline from the reference — oval, semicircle, round, rectangular, runner, or irregular.
- Do NOT regularize the shape: never convert oval to rectangle, never square off curved edges, never change proportions.
- Match the reference perimeter precisely, including curved vs straight edges and corner style.""",
    'oval': """
RUG SHAPE (CRITICAL — SYMMETRIC OVAL, DESKEWED):
- Silhouette = classic vertical oval / stadium with EQUAL top and bottom caps.
- Top cap == bottom cap (mirror across the horizontal mid-line). Never a pointier bottom.
- Broad soft rounded ends — NOT egg, NOT teardrop, NOT lemon-point tips.
- Pattern stays from the reference; outline is deskewed to orthographic symmetry.""",
    'semicircle': """
RUG SHAPE (CRITICAL — SEMICIRCLE / HALF-DISK):
- Silhouette MUST be a true semicircle (D-shape): straight diameter + half-circle arc, constant radius.
- NOT a full circle, NOT an oval, NOT a quarter-circle, NOT a rounded rectangle.
- Diameter edge perfectly straight; curved side perfectly circular (180°).
- Pattern stays from the reference; outline is corrected to geometric semicircle.""",
    'rectangular': """
RUG SHAPE (CRITICAL — RECTANGULAR):
- The rug MUST stay rectangular with the same corner style as the reference (sharp or slightly rounded corners).
- Preserve exact length-to-width ratio. Do not convert to oval or round.""",
    'round': """
RUG SHAPE (CRITICAL — FULL CIRCLE):
- The rug MUST be a perfect CIRCLE (constant radius). Not oval, not truncated, not stadium.
- The ENTIRE circumference must be visible — left, right, top, and bottom arcs fully inside the frame.
- Never clip, crop, or cut off any part of the circle edge.""",
    'runner': """
RUG SHAPE (CRITICAL — RUNNER):
- The rug MUST stay a long narrow runner (rectangular strip). Preserve exact length-to-width ratio from the reference.
- Do not convert to square, oval, or standard area rug proportions.""",
}

_SOURCE_BLOCKS = {
    'auto': """
SOURCE PHOTO:
- If the reference shows the rug on a floor or in a room, isolate ONLY the rug and remove all floorboards, tiles, furniture, and surroundings.
- Also remove any hang tag / hanger / price card attached to the rug (see hang-tag rules).""",
    'in_room': """
SOURCE PHOTO (in-room):
- The reference is a room/floor photo. Extract ONLY the rug — remove wooden floor, tiles, shadows of the room, and all background.
- Re-frame as a clean catalog product shot of the rug alone.
- Also remove any hang tag / hanger / price card attached to the rug (see hang-tag rules).""",
    'isolated': """
SOURCE PHOTO (isolated):
- The reference is already an isolated rug photo. Keep a clean tight crop to the rug edge without adding floor or background.
- If a hang tag / hanger / price card is attached, remove it and restore the rug underneath (see hang-tag rules).""",
}

_COLOR_BLOCKS = {
    'auto': """
COLOR & LIGHTING (MATCH REFERENCE EXACTLY — CRITICAL FOR BUYERS):
- Copy the reference colors, saturation, brightness, and contrast EXACTLY — no beautify, no HDR, no punchy grading.
- Do NOT increase saturation or make colors more vivid/bright than the photo (customers must not be misled).
- Do NOT deepen blacks or brighten creams beyond the reference. Keep muted/matte product look if the photo is muted.
- Lighting: same soft natural look as the reference — no harsh studio contrast, no glossy hotspots.""",
    'preserve_exact': """
COLOR & LIGHTING (PIXEL-FAITHFUL — CRITICAL FOR BUYERS):
- Match reference hues, saturation, and luminance as closely as possible. No recoloring, no color grading, no vibrance boost.
- Do NOT make the result more saturated, brighter, or higher-contrast than the source photo.
- Dark areas stay the same darkness as the photo (e.g. dark brown stays dark brown, not jet black).
- Light areas stay the same cream/beige as the photo (not brighter white).
- Lighting: soft and even like the reference — no studio punch-up.""",
    'monochrome': """
COLOR & LIGHTING (MONOCHROME — MATCH REFERENCE):
- Preserve the exact gray, charcoal, silver, and black tones from the reference without adding color.
- Do NOT boost contrast or brighten highlights beyond the photo. No punchy black-and-white look.
- Lighting: same soft balance as the reference.""",
}


def build_catalog_prompt(options: CatalogPromptOptions | None = None) -> str:
    opts = (options or CatalogPromptOptions()).normalized()

    if opts.rug_shape == 'oval':
        aspect_note = _OVAL_ASPECT_NOTE
        framing = _OVAL_FRAMING
        preservation = _OVAL_PRESERVATION
        center_line = '- Center the rug in the vertical 2:3 frame.'
    elif opts.rug_shape == 'semicircle':
        aspect_note = _SEMICIRCLE_ASPECT_NOTE
        framing = _SEMICIRCLE_FRAMING
        preservation = _SEMICIRCLE_PRESERVATION
        center_line = '- Center the rug in the vertical 2:3 frame.'
    elif opts.rug_shape == 'round':
        aspect_note = _ROUND_ASPECT_NOTE
        framing = _ROUND_FRAMING
        preservation = _ROUND_PRESERVATION
        center_line = '- Center the circle in the square 1:1 frame with equal white margin on every side.'
    else:
        aspect_note = _ASPECT_NOTE
        framing = _NO_WHITESPACE
        preservation = _PRESERVATION
        center_line = '- Center the rug in the vertical 2:3 frame.'

    return f"""Edit the provided reference image of a rug/carpet for an e-commerce catalog thumbnail.

CAMERA & COMPOSITION (change only this):
- Perfect top-down orthogonal view: camera directly above at 90 degrees, zero perspective, no tilt, no 3D angle.
- Show the entire rug fully inside the frame; crop to the rug silhouette only.
- {aspect_note}
{framing}
{center_line}

{_SHAPE_BLOCKS[opts.rug_shape]}
{_SOURCE_BLOCKS[opts.source_context]}
{_REMOVE_HANGTAG}
{_COLOR_BLOCKS[opts.color_mode]}

{preservation}

OUTPUT:
- Clean catalog product photo, sharp focus; lighting and color must stay faithful to the reference (not more vivid)."""


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
{_REMOVE_HANGTAG}
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


def _scene_scale_block(options: ScenePromptOptions) -> str:
    label = (options.size_label or '').strip()
    if not label:
        raise ValueError("build_scene_prompt requires size_label (real product size)")

    width_m = (options.width_m or '').strip()
    length_m = (options.length_m or '').strip()
    is_round = width_m and length_m and width_m == length_m

    if is_round:
        return f"""
SCALE (CRITICAL — real product size, do NOT invent another size):
- This is a ROUND rug. Catalog size label: {label}.
- Real diameter ≈ {width_m} m (same as width and length in metres).
- Scale vs known furniture: sofa seat ~2.0–2.2 m wide, coffee table ~0.9–1.2 m, doorway clear opening ~0.8–0.9 m, adult standing height ~1.7 m.
- On the floor the rug MUST appear exactly this diameter — not oversized like a living-room carpet if it is a small mat, and not undersized if it is large.
- Keep realistic contact shadows consistent with that footprint."""

    return f"""
SCALE (CRITICAL — real product size, do NOT invent another size):
- Catalog size label: {label}.
- Real footprint: {width_m} m × {length_m} m (width × length).
- Scale vs known furniture: sofa ~2.0–2.2 m, coffee table ~0.9–1.2 m, dining table ~1.6–2.0 m, doorway ~0.8–0.9 m, adult standing height ~1.7 m.
- The rug footprint on the floor MUST match these exact dimensions — do not enlarge, shrink, or substitute a different size.
- Keep realistic contact shadows consistent with that footprint."""


def build_scene_prompt(options: ScenePromptOptions | None = None) -> str:
    opts = (options or ScenePromptOptions()).normalized()
    scale_block = _scene_scale_block(opts)

    return f"""Edit the provided reference image of a rug/carpet into a photorealistic in-room lifestyle product photo for an e-commerce product page gallery.

GOAL:
- Place THIS EXACT rug (same pattern, colors, texture) naturally on the floor in a real interior scene.
- Output a horizontal 4:3 landscape image suitable for a product page slider.

{_SHAPE_BLOCKS[opts.rug_shape]}
{_REMOVE_HANGTAG}
{_COLOR_BLOCKS[opts.color_mode]}

{_ROOM_BLOCKS[opts.room_type]}
{_FLOOR_BLOCKS[opts.floor_style]}
{_DISTANCE_BLOCKS[opts.camera_distance]}
{_VIEW_BLOCKS[opts.view_angle]}
{scale_block}

STRICT PRESERVATION (do NOT change the rug):
- The rug pattern, motif layout, colors, texture, pile, and material must match the reference exactly.
- Do not redesign, recolor, simplify, or substitute a different rug.
- Preserve the rug's exact shape silhouette on the floor (oval stays oval, semicircle stays semicircle, rectangular stays rectangular).
- Hang tags/hangers/price cards are packaging props — remove them and restore the rug underneath before placing it in the scene.

SCENE RULES:
- Photorealistic interior photography, soft natural daylight, no text, no watermark, no people.
- Furniture and decor should feel premium and contemporary; do not overpower the rug.
- The rug must sit flat on the floor with realistic contact shadows matching the SCALE block above."""
