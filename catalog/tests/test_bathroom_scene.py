"""Tests: генерація інтер'єру ванної з комплекту 2 килимків."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from catalog.services.replicate_prompt_options import (
    DEFAULT_BATH_MAT_SIZE,
    GenerationOptions,
    ScenePromptOptions,
)
from catalog.services.replicate_prompts import build_scene_prompt


class BathroomOptionsTests(SimpleTestCase):
    def test_bathroom_forces_wide_framing(self):
        opts = ScenePromptOptions(
            room_type='bathroom', width_m='0.5', length_m='0.6'
        ).normalized()
        # маленькі килимки не мають заповнювати кадр
        self.assertEqual(opts.camera_distance, 'wide')

    def test_second_rug_only_for_bathroom(self):
        opts = ScenePromptOptions(room_type='living_room', second_rug=True).normalized()
        self.assertFalse(opts.second_rug)
        self.assertFalse(opts.is_bathroom_set)

    def test_is_bathroom_set(self):
        opts = ScenePromptOptions(room_type='bathroom', second_rug=True).normalized()
        self.assertTrue(opts.is_bathroom_set)

    def test_from_request_post_parses_flags(self):
        gen = GenerationOptions.from_request_post(
            {
                'room_type': 'bathroom',
                'second_rug': '1',
                'second_size_label': '0.6 × 0.9',
            }
        )
        self.assertTrue(gen.scene.is_bathroom_set)
        self.assertEqual(gen.scene.second_size_label, '0.6 × 0.9')

    def test_meta_includes_second_rug(self):
        opts = ScenePromptOptions(room_type='bathroom', second_rug=True)
        meta = opts.as_meta()
        self.assertTrue(meta['second_rug'])
        self.assertEqual(meta['second_size_label'], DEFAULT_BATH_MAT_SIZE)


class BathroomPromptTests(SimpleTestCase):
    def _prompt(self, **kwargs):
        defaults = dict(
            room_type='bathroom',
            second_rug=True,
            size_label='0.5 × 0.6',
            second_size_label='0.6 × 0.9',
        )
        defaults.update(kwargs)
        return build_scene_prompt(ScenePromptOptions(**defaults))

    def test_prompt_describes_two_distinct_rugs(self):
        p = self._prompt()
        self.assertIn('TWO SEPARATE RUGS', p)
        self.assertIn('FIRST reference', p)
        self.assertIn('SECOND reference', p)
        self.assertIn('exactly two rugs', p)

    def test_prompt_protects_toilet_cutout(self):
        p = self._prompt()
        self.assertIn('U-shaped', p)
        self.assertIn('around the base', p)
        self.assertIn('never fill it in', p)

    def test_prompt_forbids_pattern_swap(self):
        p = self._prompt()
        self.assertIn('Do NOT swap', p)
        self.assertIn('PATTERN IDENTITY', p)

    def test_prompt_uses_both_sizes(self):
        p = self._prompt()
        self.assertIn('0.5 × 0.6', p)
        self.assertIn('0.6 × 0.9', p)

    def test_prompt_camera_shows_both(self):
        p = self._prompt()
        self.assertIn('doorway', p)
        self.assertIn('not cropped', p)

    def test_prompt_forbids_extra_rugs_and_wall_to_wall(self):
        p = self._prompt()
        self.assertIn('third rug', p)
        self.assertIn('wall-to-wall', p)

    def test_extra_prompt_appended(self):
        p = self._prompt(extra_prompt='додай рушник на гачку')
        self.assertIn('додай рушник на гачку', p)

    def test_single_rug_bathroom_uses_standard_prompt(self):
        # ванна без другого фото → звичайний сценарний промпт
        p = build_scene_prompt(
            ScenePromptOptions(
                room_type='bathroom', size_label='0.5 × 0.6',
                width_m='0.5', length_m='0.6',
            )
        )
        self.assertNotIn('TWO SEPARATE RUGS', p)
        self.assertIn('bathroom', p.lower())


class BathroomServiceTests(SimpleTestCase):
    def _service(self):
        from catalog.services.replicate_product_images import (
            ReplicateProductImageService,
        )

        with patch.object(
            ReplicateProductImageService, '__init__', lambda self: None
        ):
            svc = ReplicateProductImageService()
        svc.client = MagicMock()
        from catalog.services.replicate_product_images import ReplicateJobLog

        svc.job_log = ReplicateJobLog()
        return svc

    def test_bathroom_set_requires_second_image(self):
        from catalog.services.replicate_product_images import (
            ReplicateGenerationError,
        )

        svc = self._service()
        opts = GenerationOptions()
        opts.scene = ScenePromptOptions(
            room_type='bathroom', second_rug=True, size_label='0.5 × 0.6'
        ).normalized()

        with self.assertRaises(ReplicateGenerationError) as ctx:
            svc.generate_phase(Path('fake.jpg'), 'scene', opts)
        self.assertIn('два фото', str(ctx.exception))

    @patch('catalog.services.replicate_product_images.optimize_product_image',
           side_effect=lambda b, max_width=None: b)
    def test_two_images_sent_in_order(self, _opt):
        svc = self._service()
        captured = {}

        def fake_run(source_bytes, source_name, prompt, phase_label,
                     aspect_ratio, second_bytes=None, second_name=''):
            captured['first'] = source_bytes
            captured['second'] = second_bytes
            captured['prompt'] = prompt
            return b'result'

        svc._run_and_download = fake_run

        opts = GenerationOptions()
        opts.scene = ScenePromptOptions(
            room_type='bathroom', second_rug=True,
            size_label='0.5 × 0.6', second_size_label='0.6 × 0.9',
        ).normalized()

        with patch.object(Path, 'read_bytes', autospec=True) as mock_read:
            mock_read.side_effect = [b'contour-rug', b'rect-mat']
            image, meta = svc.generate_phase(
                Path('a.jpg'), 'scene', opts,
                second_source_path=Path('b.jpg'),
            )

        # порядок критичний: промпт посилається на FIRST/SECOND
        self.assertEqual(captured['first'], b'contour-rug')
        self.assertEqual(captured['second'], b'rect-mat')
        self.assertIn('TWO SEPARATE RUGS', captured['prompt'])
        self.assertTrue(meta['prompt_options']['second_rug'])
