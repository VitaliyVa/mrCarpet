from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from catalog.services.scene_size import SceneSizeInfo

RUG_SHAPES = frozenset({'auto', 'oval', 'semicircle', 'rectangular', 'round', 'runner'})
SOURCE_CONTEXTS = frozenset({'auto', 'in_room', 'isolated'})
COLOR_MODES = frozenset({'auto', 'preserve_exact', 'monochrome'})

ROOM_TYPES = frozenset({
    'auto', 'living_room', 'bedroom', 'kids_room',
    'dining_room', 'hallway', 'office', 'bathroom',
})

# Ванна кімната — це комплект з двох килимків (контурний під унітаз +
# прямокутний під двері), тому вимагає другого референсного фото.
ROOM_TYPE_BATHROOM = 'bathroom'
# Типові розміри ванних наборів, якщо менеджер не вказав явно
DEFAULT_BATH_CONTOUR_SIZE = '0.5 × 0.6'
DEFAULT_BATH_MAT_SIZE = '0.6 × 0.9'
CAMERA_DISTANCES = frozenset({'close', 'medium', 'wide'})
VIEW_ANGLES = frozenset({'eye_level', 'high_angle', 'top_down_partial'})
FLOOR_STYLES = frozenset({'auto', 'wood', 'light_wood', 'tile', 'concrete'})

# Scene admin no longer exposes these — fixed / auto defaults
SCENE_DEFAULT_VIEW_ANGLE = 'eye_level'
SCENE_DEFAULT_COLOR_MODE = 'preserve_exact'
MAX_EXTRA_PROMPT_CHARS = 800


def _normalize(value: str, allowed: frozenset, default: str = 'auto') -> str:
    value = (value or default).strip()
    return value if value in allowed else default


def auto_camera_distance(width_m: str, length_m: str) -> str:
    """
    Pick framing from real metres so small rugs are not forced to fill ~50% of frame.
    """
    try:
        w = float(str(width_m).replace(',', '.'))
        l = float(str(length_m).replace(',', '.'))
    except (TypeError, ValueError):
        return 'medium'
    if w <= 0 or l <= 0:
        return 'medium'
    area = w * l
    longest = max(w, l)
    if longest <= 1.2 or area <= 1.6:
        return 'wide'
    if longest >= 2.5 or area >= 6.0:
        return 'close'
    return 'medium'


@dataclass
class CatalogPromptOptions:
    rug_shape: str = 'auto'
    source_context: str = 'auto'
    color_mode: str = 'auto'

    def normalized(self) -> 'CatalogPromptOptions':
        return CatalogPromptOptions(
            rug_shape=_normalize(self.rug_shape, RUG_SHAPES),
            source_context=_normalize(self.source_context, SOURCE_CONTEXTS),
            color_mode=_normalize(self.color_mode, COLOR_MODES),
        )

    def as_meta(self) -> dict:
        n = self.normalized()
        return {
            'rug_shape': n.rug_shape,
            'source_context': n.source_context,
            'color_mode': n.color_mode,
        }


@dataclass
class ScenePromptOptions:
    rug_shape: str = 'auto'
    room_type: str = 'auto'
    camera_distance: str = 'medium'  # auto from size when with_size / build
    view_angle: str = SCENE_DEFAULT_VIEW_ANGLE
    floor_style: str = 'auto'
    color_mode: str = SCENE_DEFAULT_COLOR_MODE
    size_label: str = ''
    width_m: str = ''
    length_m: str = ''
    extra_prompt: str = ''
    # Ванний комплект: другий килимок (прямокутний, під двері/раковину)
    second_rug: bool = False
    second_size_label: str = ''

    @property
    def is_bathroom_set(self) -> bool:
        return self.room_type == ROOM_TYPE_BATHROOM and self.second_rug

    def normalized(self) -> 'ScenePromptOptions':
        extra = (self.extra_prompt or '').strip()[:MAX_EXTRA_PROMPT_CHARS]
        width_m = (self.width_m or '').strip()
        length_m = (self.length_m or '').strip()
        distance = _normalize(self.camera_distance, CAMERA_DISTANCES, 'medium')
        if width_m and length_m:
            distance = auto_camera_distance(width_m, length_m)
        room_type = _normalize(self.room_type, ROOM_TYPES)
        # Ванна: килимки маленькі, потрібен ширший кадр щоб влізли обидва
        if room_type == ROOM_TYPE_BATHROOM:
            distance = 'wide'
        return ScenePromptOptions(
            rug_shape=_normalize(self.rug_shape, RUG_SHAPES),
            room_type=room_type,
            camera_distance=distance,
            view_angle=_normalize(
                self.view_angle, VIEW_ANGLES, SCENE_DEFAULT_VIEW_ANGLE
            ),
            floor_style=_normalize(self.floor_style, FLOOR_STYLES),
            color_mode=_normalize(
                self.color_mode, COLOR_MODES, SCENE_DEFAULT_COLOR_MODE
            ),
            size_label=(self.size_label or '').strip(),
            width_m=width_m,
            length_m=length_m,
            extra_prompt=extra,
            second_rug=bool(self.second_rug) and room_type == ROOM_TYPE_BATHROOM,
            second_size_label=(self.second_size_label or '').strip(),
        )

    def with_size(self, size_info: 'SceneSizeInfo') -> 'ScenePromptOptions':
        n = self.normalized()
        width_m = str(size_info.width_m)
        length_m = str(size_info.length_m)
        distance = auto_camera_distance(width_m, length_m)
        if n.room_type == ROOM_TYPE_BATHROOM:
            distance = 'wide'
        return ScenePromptOptions(
            rug_shape=n.rug_shape,
            room_type=n.room_type,
            camera_distance=distance,
            view_angle=SCENE_DEFAULT_VIEW_ANGLE,
            floor_style=n.floor_style,
            color_mode=SCENE_DEFAULT_COLOR_MODE,
            size_label=size_info.label,
            width_m=width_m,
            length_m=length_m,
            extra_prompt=n.extra_prompt,
            second_rug=n.second_rug,
            second_size_label=n.second_size_label,
        )

    def as_meta(self) -> dict:
        n = self.normalized()
        meta = {
            'rug_shape': n.rug_shape,
            'room_type': n.room_type,
            'camera_distance': n.camera_distance,
            'view_angle': n.view_angle,
            'floor_style': n.floor_style,
            'color_mode': n.color_mode,
        }
        if n.size_label:
            meta['size_label'] = n.size_label
            meta['width_m'] = n.width_m
            meta['length_m'] = n.length_m
        if n.extra_prompt:
            meta['extra_prompt'] = n.extra_prompt
        if n.second_rug:
            meta['second_rug'] = True
            meta['second_size_label'] = n.second_size_label or DEFAULT_BATH_MAT_SIZE
        return meta


@dataclass
class GenerationOptions:
    catalog: CatalogPromptOptions = field(default_factory=CatalogPromptOptions)
    scene: ScenePromptOptions = field(default_factory=ScenePromptOptions)

    @classmethod
    def from_request_post(cls, post) -> 'GenerationOptions':
        return cls(
            catalog=CatalogPromptOptions(
                rug_shape=(post.get('rug_shape') or 'auto').strip(),
                source_context=(post.get('source_context') or 'auto').strip(),
                color_mode=(post.get('color_mode') or 'auto').strip(),
            ).normalized(),
            scene=ScenePromptOptions(
                rug_shape=(post.get('rug_shape') or 'auto').strip(),
                room_type=(post.get('room_type') or 'auto').strip(),
                floor_style=(post.get('floor_style') or 'auto').strip(),
                view_angle=SCENE_DEFAULT_VIEW_ANGLE,
                color_mode=SCENE_DEFAULT_COLOR_MODE,
                extra_prompt=(post.get('extra_prompt') or '').strip(),
                second_rug=str(post.get('second_rug') or '').lower()
                in ('1', 'true', 'on', 'yes'),
                second_size_label=(post.get('second_size_label') or '').strip(),
            ).normalized(),
        )
