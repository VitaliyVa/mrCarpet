"""
Prompt builders for Replicate product-image generation.

Keep prompt text here (not in views) so we can version and A/B test without
touching Django admin / HTTP layers.
"""

from __future__ import annotations

from catalog.services.replicate_prompt_options import (
    CatalogPromptOptions,
    ScenePromptOptions,
)

PROMPT_VERSION = 'v5-scene-scale-auto'


# ---------------------------------------------------------------------------
# Catalog / hover blocks (unchanged intent)
# ---------------------------------------------------------------------------

_SHAPE_BLOCKS = {
    'auto': (
        'Preserve the exact silhouette of the rug from the reference. '
        'Do not invent a different outline.'
    ),
    'oval': (
        'The rug must be a clear oval: elongated elliptical silhouette, '
        'smooth continuous curve, no sharp corners. Not a circle, not a rectangle.'
    ),
    'semicircle': (
        'The rug must be a clear semicircle (half-moon): one straight diameter edge '
        'and one smooth semicircular arc. Not a full circle, not a rectangle.'
    ),
    'rectangular': (
        'The rug must be rectangular or nearly rectangular with four clear corners '
        'and straight sides (slight soft corners OK if present in the reference).'
    ),
    'round': (
        'The rug must be a clear circle (round rug): equal width and length, '
        'smooth continuous curve all around. Not an oval, not a rectangle.'
    ),
    'runner': (
        'The rug must be a long narrow runner: much longer than wide, '
        'rectangular silhouette suitable for a hallway.'
    ),
}

_SOURCE_CONTEXT_BLOCKS = {
    'auto': '',
    'in_room': (
        'The reference photo shows the rug already placed in a room or on a floor. '
        'Ignore the room, furniture, walls, and floor around it. Extract only the rug itself.'
    ),
    'isolated': (
        'The reference photo already shows the rug isolated (studio / cutout / plain backdrop). '
        'Keep that isolation; do not invent a room around it in this step.'
    ),
}

_COLOR_MODE_BLOCKS = {
    'auto': '',
    'preserve_exact': (
        'COLOR LOCK: Keep the exact hue, saturation, and brightness of the rug pattern '
        'from the reference. Do not shift toward warmer, cooler, greyer, or more vivid tones.'
    ),
    'monochrome': (
        'COLOR INTENT: Render the rug as a tasteful monochrome / greyscale interpretation '
        'of the reference pattern (black, white, and greys only), while keeping pattern structure.'
    ),
}

_ROOM_TYPE_BLOCKS = {
    'auto': (
        'Choose a tasteful residential interior that fits the rug size and style.'
    ),
    'living_room': (
        'Setting: a bright modern living room with a sofa and coffee table as scale anchors.'
    ),
    'bedroom': (
        'Setting: a calm modern bedroom; bed or nightstands may appear as scale anchors.'
    ),
    'kids_room': (
        'Setting: a tidy kids room with playful but clean décor; furniture for scale only.'
    ),
    'dining_room': (
        'Setting: a dining area with a table and chairs as scale anchors.'
    ),
    'hallway': (
        'Setting: a residential hallway / corridor with visible floor length for scale.'
    ),
    'office': (
        'Setting: a home office / study with a desk or bookshelf as scale anchors.'
    ),
}

# Frame occupancy — used AFTER real metres are known; auto-picked from size.
_DISTANCE_BLOCKS = {
    'close': (
        'CAMERA DISTANCE: closer framing. The rug may occupy roughly 40–55% of the frame width, '
        'but MUST still match the real metres below — never stretch a small rug to fill the floor.'
    ),
    'medium': (
        'CAMERA DISTANCE: medium wide shot. The rug occupies roughly 25–40% of the frame width. '
        'Plenty of floor and furniture must remain visible around the rug.'
    ),
    'wide': (
        'CAMERA DISTANCE: wide establishing shot of the whole room. '
        'The rug is a SMALL object in the scene — roughly 15–30% of the frame width only. '
        'Most of the image is furniture, walls, and empty floor. Do NOT zoom in on the rug.'
    ),
}

_VIEW_ANGLE_BLOCKS = {
    'eye_level': (
        'CAMERA ANGLE: natural standing eye-level three-quarter view into the room '
        '(slight downward tilt is OK). Not a flat top-down plan view.'
    ),
    'high_angle': (
        'CAMERA ANGLE: high three-quarter view looking down into the room, '
        'still showing walls and furniture depth — not a pure orthographic top-down.'
    ),
    'top_down_partial': (
        'CAMERA ANGLE: steep high angle, almost top-down, but keep a little perspective '
        'so the room does not look like a flat diagram.'
    ),
}

_FLOOR_STYLE_BLOCKS = {
    'auto': 'Floor: realistic residential flooring that fits the room.',
    'wood': 'Floor: medium-tone natural wood planks.',
    'light_wood': 'Floor: light oak / light wood planks.',
    'tile': 'Floor: large-format light ceramic or stone tiles.',
    'concrete': 'Floor: smooth polished concrete or microcement.',
}


def _shape_block(options: CatalogPromptOptions | ScenePromptOptions) -> str:
    return _SHAPE_BLOCKS.get(options.rug_shape, _SHAPE_BLOCKS['auto'])


def _relative_size_sentence(width_m: float, length_m: float, is_round: bool) -> str:
    sofa_w = 2.1
    coffee_w = 1.1
    longest = max(width_m, length_m)
    shortest = min(width_m, length_m)
    parts = [
        f'This rug is {width_m:.1f} m × {length_m:.1f} m in real life',
        f'(about {shortest:.1f} m on the short side, {longest:.1f} m on the long side)',
    ]
    if is_round:
        parts.append(f'— a ROUND rug roughly {width_m:.1f} m across')
    if longest < sofa_w * 0.75:
        parts.append(
            f'. Relatively SMALL: clearly shorter than a typical 2.1 m sofa; '
            f'closer in scale to a coffee table (~{coffee_w:.1f} m) than to wall-to-wall coverage'
        )
    elif longest < sofa_w * 1.15:
        parts.append(
            '. Medium size: similar length to a sofa, still leaving large floor margins'
        )
    else:
        parts.append(
            '. Large area rug — still must leave visible floor margins; not wall-to-wall carpeting'
        )
    return ''.join(parts) + '.'


def _scene_scale_block(options: ScenePromptOptions) -> str:
    if not options.width_m or not options.length_m:
        return (
            'SCALE: Size is unknown — keep the rug modest in the frame with clear floor margins; '
            'never cover the whole floor wall-to-wall.'
        )
    try:
        w = float(options.width_m)
        l = float(options.length_m)
    except (TypeError, ValueError):
        return (
            f'SCALE (CRITICAL): Real rug size is {options.size_label}. '
            'Match that physical size; leave floor margins; not wall-to-wall.'
        )

    is_round = abs(w - l) < 0.05 and options.rug_shape in ('round', 'auto')
    relative = _relative_size_sentence(w, l, is_round)
    label = options.size_label or f'{options.width_m}×{options.length_m}'

    return (
        f'SCALE (CRITICAL — HIGHEST PRIORITY, overrides camera framing habits):\n'
        f'- Real product size: {label} = EXACTLY {options.width_m} metres × '
        f'{options.length_m} metres on the floor.\n'
        f'- {relative}\n'
        f'- The reference photo is a CLOSE-UP / cutout of the rug pattern ONLY. '
        f'It does NOT show true room scale. IGNORE how large the rug looks in the reference image.\n'
        f'- Place furniture that proves scale: sofa (~2.1 m wide), coffee table (~1.0–1.2 m), '
        f'or dining chairs. The rug MUST look correctly small/large next to those objects.\n'
        f'- Leave generous empty floor around the rug. Anti-patterns (FORBIDDEN): '
        f'wall-to-wall carpet, rug touching all four walls, rug filling most of the room, '
        f'rug looking like a 3×4 m or larger piece when it is only {options.width_m}×{options.length_m} m.\n'
        f'- Repeat: physical size on the floor is {options.width_m} m by {options.length_m} m — nothing bigger.'
    )


def build_catalog_prompt(options: CatalogPromptOptions | None = None) -> str:
    options = (options or CatalogPromptOptions()).normalized()
    parts = [
        (
            'Create a clean e-commerce product photo of ONLY the rug from the reference image. '
            'Photorealistic, studio quality. Soft even lighting, no harsh shadows. '
            'Pure white or very light grey seamless background. '
            'The rug lies flat, fully visible, sharp focus, high detail on the pile and pattern. '
            'No people, no furniture, no room, no text, no watermark, no logo, no props.'
        ),
        _shape_block(options),
    ]
    src = _SOURCE_CONTEXT_BLOCKS.get(options.source_context, '')
    if src:
        parts.append(src)
    color = _COLOR_MODE_BLOCKS.get(options.color_mode, '')
    if color:
        parts.append(color)
    parts.append(
        'Preserve the exact pattern, colors, proportions, and fringe/edge details from the reference. '
        'Do not invent a new design.'
    )
    return ' '.join(parts)


def build_hover_prompt(options: CatalogPromptOptions | None = None) -> str:
    options = (options or CatalogPromptOptions()).normalized()
    parts = [
        (
            'Create a photorealistic close-up detail / texture shot of the SAME rug from the reference. '
            'Show pile depth, weave, and pattern detail. Soft studio lighting. '
            'Neutral background. No people, no furniture, no text, no watermark.'
        ),
        _shape_block(options),
    ]
    color = _COLOR_MODE_BLOCKS.get(options.color_mode, '')
    if color:
        parts.append(color)
    parts.append(
        'Keep pattern identity identical to the reference; this is a detail crop / texture view, not a new design.'
    )
    return ' '.join(parts)


def build_scene_prompt(options: ScenePromptOptions | None = None) -> str:
    options = (options or ScenePromptOptions()).normalized()
    parts = [
        (
            'Place the EXACT rug from the reference image into a photorealistic residential interior. '
            'The rug pattern, colors, and silhouette must match the reference. '
            'Natural daylight, believable materials, no people, no text, no watermark, no logo.'
        ),
        _scene_scale_block(options),
        _ROOM_TYPE_BLOCKS.get(options.room_type, _ROOM_TYPE_BLOCKS['auto']),
        _DISTANCE_BLOCKS.get(options.camera_distance, _DISTANCE_BLOCKS['medium']),
        _VIEW_ANGLE_BLOCKS.get(options.view_angle, _VIEW_ANGLE_BLOCKS['eye_level']),
        _FLOOR_STYLE_BLOCKS.get(options.floor_style, _FLOOR_STYLE_BLOCKS['auto']),
        _shape_block(options),
        _COLOR_MODE_BLOCKS.get(options.color_mode, _COLOR_MODE_BLOCKS['preserve_exact']),
        (
            'COMPOSITION: show enough of the room that the rug size is obvious. '
            'Do not crop so tight that scale cannot be judged.'
        ),
    ]
    if options.extra_prompt:
        parts.append(
            f'ADDITIONAL MANAGER NOTES (follow if compatible with scale and pattern fidelity): '
            f'{options.extra_prompt}'
        )
    return '\n\n'.join(p for p in parts if p)
