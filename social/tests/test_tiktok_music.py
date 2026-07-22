"""
Tests: the background-music rotation.

Two days in a row of one melody is exactly what a listener notices, so the
rotation is round-robin rather than seeded-random — random collided often
enough to ship the same track on consecutive picks.
"""

from unittest.mock import patch

from django.test import SimpleTestCase

from social.services import tiktok_music
from social.services.tiktok_music import pick_track


class PickTrackTests(SimpleTestCase):
    TRACKS = [f"social/tiktok/music/track-{i:02d}.wav" for i in range(1, 6)]

    def _with_library(self, tracks):
        return patch.object(tiktok_music, "library_paths", return_value=tracks)

    def test_consecutive_picks_never_share_a_track(self):
        with self._with_library(self.TRACKS):
            chosen = [pick_track(pk) for pk in range(100, 130)]
        for a, b in zip(chosen, chosen[1:]):
            self.assertNotEqual(a, b)

    def test_same_pick_keeps_its_track(self):
        """A regenerated video must not swap its music."""
        with self._with_library(self.TRACKS):
            self.assertEqual(pick_track(7), pick_track(7))

    def test_empty_library_falls_back_to_silence(self):
        with self._with_library([]):
            self.assertEqual(pick_track(3), "")

    def test_hand_picked_formats_are_accepted(self):
        """Uploaded mp3/m4a tracks join the rotation alongside generated wavs."""
        files = ["track-01.wav", "nice-song.mp3", "another.M4A", "notes.txt"]
        with patch.object(
            tiktok_music.default_storage, "listdir", return_value=([], files)
        ):
            paths = tiktok_music.library_paths()
        self.assertEqual(len(paths), 3)
        self.assertTrue(all(p.startswith(tiktok_music.MUSIC_DIR) for p in paths))
        self.assertFalse(any(p.endswith(".txt") for p in paths))
