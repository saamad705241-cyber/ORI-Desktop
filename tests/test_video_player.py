import tempfile
import unittest
from pathlib import Path

from actions.video_player import video_player


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


if __name__ == "__main__":
    unittest.main()
