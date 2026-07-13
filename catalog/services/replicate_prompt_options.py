from dataclasses import dataclass, field

RUG_SHAPES = frozenset({'auto', 'oval', 'rectangular', 'round', 'runner'})
SOURCE_CONTEXTS = frozenset({'auto', 'in_room', 'isolated'})
COLOR_MODES = frozenset({'auto', 'preserve_exact', 'monochrome'})

ROOM_TYPES = frozenset({
    'auto', 'living_room', 'bedroom', 'kids_room',
    'dining_room', 'hallway', 'office',
})
CAMERA_DISTANCES = frozenset({'close', 'medium', 'wide'})
VIEW_ANGLES = frozenset({'eye_level', 'high_angle', 'top_down_partial'})
FLOOR_STYLES = frozenset({'auto', 'wood', 'light_wood', 'tile', 'concrete'})


def _normalize(value: str, allowed: frozenset, default: str = 'auto') -> str:
    value = (value or default).strip()
    return value if value in allowed else default


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
    camera_distance: str = 'medium'
    view_angle: str = 'eye_level'
    floor_style: str = 'auto'
    color_mode: str = 'auto'

    def normalized(self) -> 'ScenePromptOptions':
        return ScenePromptOptions(
            rug_shape=_normalize(self.rug_shape, RUG_SHAPES),
            room_type=_normalize(self.room_type, ROOM_TYPES),
            camera_distance=_normalize(self.camera_distance, CAMERA_DISTANCES, 'medium'),
            view_angle=_normalize(self.view_angle, VIEW_ANGLES, 'eye_level'),
            floor_style=_normalize(self.floor_style, FLOOR_STYLES),
            color_mode=_normalize(self.color_mode, COLOR_MODES),
        )

    def as_meta(self) -> dict:
        n = self.normalized()
        return {
            'rug_shape': n.rug_shape,
            'room_type': n.room_type,
            'camera_distance': n.camera_distance,
            'view_angle': n.view_angle,
            'floor_style': n.floor_style,
            'color_mode': n.color_mode,
        }


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
                camera_distance=(post.get('camera_distance') or 'medium').strip(),
                view_angle=(post.get('view_angle') or 'eye_level').strip(),
                floor_style=(post.get('floor_style') or 'auto').strip(),
                color_mode=(post.get('color_mode') or 'auto').strip(),
            ).normalized(),
        )
