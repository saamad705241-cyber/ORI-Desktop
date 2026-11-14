import tempfile
import unittest
from pathlib import Path

from actions.video_player import _best_video_format, video_player


class _MockPlayer:
    def __init__(self, playing=False):
        self._playing = playing
        self.stopped = 0
        self.shown = []

    def video_is_playing(self):
        return self._playing

    def stop_video(self):
        self.stopped += 1
        self._playing = False

    def show_video(self, source, title="", muted=True, audio_source=""):
        self.shown.append(
            {
                "source": source,
                "title": title,
                "muted": muted,
                "audio_source": audio_source,
            }
        )
        self._playing = True


class VideoPlayerTests(unittest.TestCase):
    def test_local_file_replaces_current_video_before_playing(self):
        with tempfile.TemporaryDirectory() as tmp:
            clip = Path(tmp) / "song.mp4"
            clip.write_bytes(b"fake")
            player = _MockPlayer(playing=True)

            out = video_player(
                {"action": "play", "source": str(clip)},
                player=player,
            )

            self.assertEqual(out, "Playing song.mp4 on the display, muted. Qt playback was confirmed.")
            self.assertEqual(player.stopped, 1)
            self.assertEqual(len(player.shown), 1)
            self.assertEqual(player.shown[0]["source"], str(clip))
            self.assertTrue(player.shown[0]["muted"])

    def test_direct_url_replaces_current_video_before_playing(self):
        player = _MockPlayer(playing=True)

        out = video_player(
            {"action": "play", "source": "https://example.com/test.mp4"},
            player=player,
        )

        self.assertEqual(out, "Playing that on the display, muted. Qt playback was confirmed.")
        self.assertEqual(player.stopped, 1)
        self.assertEqual(len(player.shown), 1)
        self.assertEqual(player.shown[0]["source"], "https://example.com/test.mp4")


    def test_video_selector_prefers_full_hd_but_caps_normal_selection_at_1080p(self):
        formats = [
            {"format_id": "720", "height": 720, "vcodec": "avc1.64001f", "ext": "mp4", "tbr": 2600},
            {"format_id": "1080", "height": 1080, "vcodec": "avc1.640028", "ext": "mp4", "tbr": 4200},
            {"format_id": "1440", "height": 1440, "vcodec": "avc1.640033", "ext": "mp4", "tbr": 6800},
            {"format_id": "2160", "height": 2160, "vcodec": "av01.0.12M.08", "ext": "mp4", "tbr": 12000},
        ]

        selected = _best_video_format(formats)

        self.assertEqual(selected["format_id"], "1080")

    def test_video_selector_prefers_h264_mp4_when_resolution_matches(self):
        formats = [
            {"format_id": "vp9", "height": 1080, "vcodec": "vp9", "ext": "webm", "tbr": 7200},
            {"format_id": "h264", "height": 1080, "vcodec": "avc1.640028", "ext": "mp4", "tbr": 4300},
        ]

        selected = _best_video_format(formats)

        self.assertEqual(selected["format_id"], "h264")

    def test_video_selector_uses_smallest_available_stream_when_all_exceed_1080p(self):
        formats = [
            {"format_id": "2160", "height": 2160, "vcodec": "av01", "ext": "mp4", "tbr": 12000},
            {"format_id": "1440", "height": 1440, "vcodec": "avc1", "ext": "mp4", "tbr": 7000},
        ]

        selected = _best_video_format(formats)

        self.assertEqual(selected["format_id"], "1440")

    def test_video_selector_handles_missing_height_and_empty_formats(self):
        formats = [{"format_id": "unknown", "vcodec": "avc1", "ext": "mp4", "tbr": 900}]

        self.assertEqual(_best_video_format(formats)["format_id"], "unknown")
        self.assertIsNone(_best_video_format([]))


if __name__ == "__main__":
    unittest.main()
