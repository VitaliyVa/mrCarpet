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


class ChorusOffsetTests(SimpleTestCase):
    """
    A hand-picked track runs 2+ minutes and second 0 is the intro. The montage
    should start where the song is loudest — the chorus — and the cut should
    land on a quiet chunk so it does not slice a note in half.
    """

    @staticmethod
    def _chunks(levels, step=0.5):
        return [(i * step, db) for i, db in enumerate(levels)]

    def test_quiet_intro_loud_chorus(self):
        # 30s of -40dB intro, then 30s of -12dB chorus, then -30dB outro.
        levels = [-40.0] * 60 + [-12.0] * 60 + [-30.0] * 60
        offset = tiktok_music._choose_offset(self._chunks(levels), duration=14.0)
        self.assertGreaterEqual(offset, 28.0)
        self.assertLessEqual(offset, 31.0)

    def test_cut_snaps_to_the_quietest_nearby_chunk(self):
        # The breath before the drop: one dip right where the chorus begins.
        levels = [-30.0] * 40 + [-55.0] + [-10.0] * 60
        offset = tiktok_music._choose_offset(self._chunks(levels), duration=10.0)
        self.assertEqual(offset, 20.0)  # the -55dB chunk at t=20.0

    def test_track_barely_longer_than_the_window_starts_at_zero(self):
        levels = [-20.0] * 30  # 15s track, 14s window
        offset = tiktok_music._choose_offset(self._chunks(levels), duration=14.0)
        self.assertEqual(offset, 0.0)

    def test_short_generated_track_is_never_seeked(self):
        """The 16s library keeps its old behaviour: play from the top, loop."""
        chunks = self._chunks([-20.0] * 32)  # 16 seconds
        with patch.object(tiktok_music, "_rms_chunks", return_value=chunks):
            self.assertEqual(tiktok_music.chorus_offset("x.wav", 13.5), 0.0)

    def test_analysis_failure_falls_back_to_zero(self):
        with patch.object(
            tiktok_music, "_rms_chunks", side_effect=RuntimeError("no ffmpeg")
        ):
            self.assertEqual(tiktok_music.chorus_offset("x.mp3", 13.5), 0.0)

    def test_empty_analysis_falls_back_to_zero(self):
        with patch.object(tiktok_music, "_rms_chunks", return_value=[]):
            self.assertEqual(tiktok_music.chorus_offset("x.mp3", 13.5), 0.0)
