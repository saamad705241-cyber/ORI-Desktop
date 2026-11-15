from __future__ import annotations

import argparse
from pathlib import Path


VOICE_LEVELER = '''"""Gentle stateful loudness control for streamed ORI speech PCM."""
from __future__ import annotations

import math

import numpy as np


class VoiceLeveler:
    """Smooth chunk-to-chunk speech level without normalising silence.

    The processor operates on little-endian mono int16 PCM. Gain reduction is
    relatively fast, gain recovery is deliberately slower to avoid audible
    pumping. A final peak guard prevents clipping after gain is applied.
    """

    def __init__(
        self,
        sample_rate: int = 24_000,
        target_rms: float = 0.105,
        min_gain: float = 0.70,
        max_gain: float = 1.50,
        attack_seconds: float = 0.08,
        release_seconds: float = 0.45,
        gate_rms: float = 0.012,
        peak_limit: int = 30_000,
    ) -> None:
        self.sample_rate = max(1, int(sample_rate))
        self.target_rms = max(0.001, float(target_rms))
        self.min_gain = max(0.05, float(min_gain))
        self.max_gain = max(self.min_gain, float(max_gain))
        self.attack_seconds = max(0.01, float(attack_seconds))
        self.release_seconds = max(0.02, float(release_seconds))
        self.gate_rms = max(0.0, float(gate_rms))
        self.peak_limit = max(1, min(32767, int(peak_limit)))
        self.gain = 1.0

    def reset(self) -> None:
        self.gain = 1.0

    def process(self, pcm: bytes | bytearray | memoryview) -> bytes:
        raw = bytes(pcm or b"")
        if len(raw) < 2:
            return raw
        usable = raw[: len(raw) - (len(raw) % 2)]
        samples = np.frombuffer(usable, dtype="<i2")
        if samples.size == 0:
            return raw

        audio = samples.astype(np.float32) / 32768.0
        rms = float(np.sqrt(np.mean(audio * audio)))
        if math.isfinite(rms) and rms >= self.gate_rms:
            desired = self.target_rms / max(rms, 1e-6)
            desired = min(self.max_gain, max(self.min_gain, desired))
            duration = samples.size / float(self.sample_rate)
            time_constant = (
                self.attack_seconds if desired < self.gain else self.release_seconds
            )
            smoothing = math.exp(-duration / time_constant)
            self.gain = smoothing * self.gain + (1.0 - smoothing) * desired

        processed = audio * self.gain
        peak = float(np.max(np.abs(processed))) if processed.size else 0.0
        limit = self.peak_limit / 32768.0
        if peak > limit:
            processed *= limit / peak
        output = np.clip(processed * 32768.0, -32768, 32767).astype("<i2")
        return output.tobytes() + raw[len(usable):]
'''


def replace_once(path: Path, old: str, new: str, *, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        if new in text:
            return
        raise RuntimeError(f"Expected patch anchor not found in {path}: {label}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")


def patch(source: Path) -> None:
    if not (source / "main.py").is_file() or not (source / "ori_metadata.py").is_file():
        raise RuntimeError(f"Not an ORI source root: {source}")

    # 3.6.6 version metadata and installer fallback.
    replace_once(
        source / "ori_metadata.py",
        'APP_VERSION = "3.6.5"',
        'APP_VERSION = "3.6.6"',
        label="application version",
    )
    replace_once(
        source / "installer" / "ORI.iss",
        '#define MyAppVersion "3.6.5"',
        '#define MyAppVersion "3.6.6"',
        label="Inno Setup fallback version",
    )

    # Smooth voice loudness and recover the current PCM batch after output underflow.
    (source / "core" / "voice_leveler.py").write_text(VOICE_LEVELER, encoding="utf-8")
    replace_once(
        source / "main.py",
        '''from core.audio_stream         import (
    append_transcript_fragment, collect_audio_batch, enqueue_audio_bytes, extract_audio_parts,
)''',
        '''from core.audio_stream         import (
    append_transcript_fragment, collect_audio_batch, enqueue_audio_bytes, extract_audio_parts,
)
from core.voice_leveler        import VoiceLeveler''',
        label="voice leveler import",
    )
    replace_once(
        source / "main.py",
        '''    async def _play_audio(self):
        print("[ORI] 🔊 Play started")

        _spk_name = get_output_device()''',
        '''    async def _play_audio(self):
        print("[ORI] 🔊 Play started")
        voice_leveler = VoiceLeveler(sample_rate=RECEIVE_SAMPLE_RATE)

        _spk_name = get_output_device()''',
        label="voice leveler setup",
    )
    replace_once(
        source / "main.py",
        '''                self._audio_output_primed = True

                # Feed the same waveform from the actual PCM being sent to speakers.
                # The HUD uses a loudness envelope to animate the signal waveform.
                try:
                    pcm = np.frombuffer(bytes(batch), dtype=np.int16)''',
        '''                self._audio_output_primed = True
                # Stabilise speech loudness with a bounded, stateful leveler.
                # Echo cancellation observes the exact processed PCM sent to speakers.
                batch = voice_leveler.process(batch)

                # Feed the same waveform from the actual PCM being sent to speakers.
                # The HUD uses a loudness envelope to animate the signal waveform.
                try:
                    pcm = np.frombuffer(bytes(batch), dtype=np.int16)''',
        label="voice leveler audio path",
    )
    replace_once(
        source / "main.py",
        '''                    if "underflow" in detail.lower() or getattr(exc, "code", None) == -9980:
                        # PortAudio can report a buffer underflow while keeping
                        # the output stream usable. Continue receiving audio;
                        # do not tear down the whole Gemini Live session.
                        continue
                    try:
                        stream.stop()
                        stream.close()
                    except Exception:
                        pass
                    try:
                        stream = _open_spk(_spk_dev)
                    except Exception:
                        stream = _open_spk(None)
                    await asyncio.get_running_loop().run_in_executor(self._audio_executor, stream.write, batch)''',
        '''                    if "underflow" in detail.lower() or getattr(exc, "code", None) == -9980:
                        # The previous path discarded the current speech batch.
                        # Reopen the endpoint and retry this batch once instead.
                        try:
                            stream.stop()
                            stream.close()
                        except Exception:
                            pass
                        try:
                            stream = _open_spk(_spk_dev)
                            await asyncio.get_running_loop().run_in_executor(
                                self._audio_executor, stream.write, batch
                            )
                        except Exception as retry_exc:
                            try:
                                stream = _open_spk(None)
                                await asyncio.get_running_loop().run_in_executor(
                                    self._audio_executor, stream.write, batch
                                )
                            except Exception as fallback_exc:
                                self.ui.write_log(
                                    f"SYS: Speaker recovery could not replay one audio batch: "
                                    f"{type(fallback_exc).__name__}. Continuing with the next chunk."
                                )
                        continue
                    try:
                        stream.stop()
                        stream.close()
                    except Exception:
                        pass
                    try:
                        stream = _open_spk(_spk_dev)
                    except Exception:
                        stream = _open_spk(None)
                    await asyncio.get_running_loop().run_in_executor(self._audio_executor, stream.write, batch)''',
        label="speaker underflow recovery",
    )

    # Media audio starts on for an explicit play request. Mute only on request.
    replace_once(
        source / "actions" / "video_player.py",
        '''SOUND IS OFF UNTIL ASKED FOR
    A soundtrack talking over the assistant is the one way this feature could
    make ORI worse rather than better, and the microphone is open while it
    plays. So it starts muted, and the user turns sound on — from the button in
    the video header, or by saying so. Closing it works both ways too.''',
        '''SOUND IS ON FOR USER-REQUESTED PLAYBACK
    A request to play a song or video normally means the user wants to hear it.
    Playback therefore starts with sound on unless the user explicitly asks for
    silence. The microphone is automatically muted while media sound is active
    and is restored when the media is muted or closed.''',
        label="media sound policy",
    )
    replace_once(source / "actions" / "video_player.py",
                 'player.show_video(local, Path(local).name, muted=True)',
                 'player.show_video(local, Path(local).name, muted=False)',
                 label="local media sound")
    replace_once(source / "actions" / "video_player.py",
                 'return f"Playing {Path(local).name} on the display, muted. Qt playback was confirmed."',
                 'return f"Playing {Path(local).name} with sound on. Qt playback was confirmed."',
                 label="local media result")
    replace_once(source / "actions" / "video_player.py",
                 'player.show_video(source, source.rsplit("/", 1)[-1][:44], muted=True)',
                 'player.show_video(source, source.rsplit("/", 1)[-1][:44], muted=False)',
                 label="direct URL sound")
    replace_once(source / "actions" / "video_player.py",
                 'return "Playing that on the display, muted. Qt playback was confirmed."',
                 'return "Playing that with sound on. Qt playback was confirmed."',
                 label="direct URL result")
    replace_once(source / "actions" / "video_player.py",
                 'player.show_video(url, title or source, muted=True,\n                              audio_source=audio_url)',
                 'player.show_video(url, title or source, muted=False,\n                              audio_source=audio_url)',
                 label="YouTube sound")
    replace_once(
        source / "actions" / "video_player.py",
        '''        "Video always starts MUTED — only call action='unmute' when the user "
        "actually asks to hear it. "''',
        '''        "Playback starts with SOUND ON because an explicit play request means "
        "the user wants to hear it. Only mute when the user specifically asks "
        "for silent playback. The microphone is automatically paused while "
        "media sound is active and restored when playback is muted or closed. "''',
        label="media tool instructions",
    )

    replace_once(
        source / "actions" / "youtube_video.py",
        "def _handle_play(parameters: dict, player) -> str:\n    query = parameters.get(\"query\", \"\").strip()\n    if not query:\n        return \"Please tell me what you'd like to watch, sir.\"\n\n    if player:\n        player.write_log(f\"[YouTube] Searching: {query}\")\n\n    print(f\"[YouTube] 🔍 Scraping first non-Shorts video for: {query}\")\n\n    video_url = _scrape_first_video_url(query)\n\n    if video_url:\n        print(f\"[YouTube] ▶️ Opening: {video_url}\")\n        _open_url(video_url)\n        return f\"Playing: {query}\"\n\n    print(\"[YouTube] ⚠️ Scrape failed, opening filtered search page\")\n    fallback_url = (\n        f\"https://www.youtube.com/results\"\n        f\"?search_query={quote_plus(query)}\"\n        f\"&sp={_YT_VIDEO_FILTER}\"\n    )\n    _open_url(fallback_url)\n    return f\"Opened YouTube search for: {query} (manual selection required)\"",
        "def _handle_play(parameters: dict, player) -> str:\n    \"\"\"Compatibility route: requested playback always uses ORI's managed media player.\"\"\"\n    query = str(parameters.get(\"query\", \"\") or \"\").strip()\n    if not query:\n        return \"Please tell me what song or video you'd like to play.\"\n    if player:\n        player.write_log(f\"[Media] Opening requested playback: {query}\")\n    try:\n        from actions.video_player import video_player\n        result = video_player({\"action\": \"play\", \"source\": query}, player=player)\n        return str(result or \"Media playback request did not return a confirmation.\")\n    except Exception as exc:\n        return f\"Media playback could not be started: {type(exc).__name__}: {exc}\"",
        label="delegate legacy YouTube play action to ORI media player",
    )
    replace_once(
        source / "actions" / "youtube_video.py",
        "\"description\": \"play | summarize | get_info | trending (default: play)\"",
        "\"description\": \"play (compatibility alias to video_player) | summarize | get_info | trending\"",
        label="document YouTube play compatibility delegation",
    )
    replace_once(
        source / "actions" / "youtube_video.py",
        '''    if player:
        player.write_log(f"[Media] Opening requested playback: {query}")''',
        '''    if player is not None and callable(getattr(player, "write_log", None)):
        player.write_log(f"[Media] Opening requested playback: {query}")''',
        label="guard optional media log interface",
    )
    # Route explicit song/music requests through the player that owns the audio stream.
    replace_once(
        source / "actions" / "video_player.py",
        '''        "Plays a VIDEO on the assistant's own display in the central visualisation area "''',
        '''        "Plays MUSIC, SONGS and VIDEOS through ORI's central display player; "''',
        label="media tool music capability",
    )
    replace_once(
        source / "actions" / "video_player.py",
        '''        "user wants to WATCH something on screen: 'play the new Dune trailer', "''',
        '''        "user wants to PLAY or HEAR music/songs, or WATCH something on screen: "
        "'play Arijit Singh songs', 'play this song', 'listen to music', "
        "'play the new Dune trailer', "''',
        label="route natural-language song requests",
    )
    replace_once(
        source / "actions" / "video_player.py",
        '''        "Do NOT use 'youtube_video' for this: that optional plugin opens videos "''',
        '''        "Do NOT use 'youtube_video' for playback: its play action only opens a browser page. "''',
        label="prefer ORI-managed playback over browser-only YouTube",
    )
    replace_once(
        source / "actions" / "youtube_video.py",
        '''    "description": "Controls YouTube. Use for: playing videos, summarizing a video's content, getting video info, or showing trending videos.",''',
        '''    "description": (
        "Use only for summarizing a YouTube video's content, getting video information, "
        "or showing trending videos. Do NOT use this tool to play music, songs or videos: "
        "its play action only opens a browser page and does not manage ORI's media audio. "
        "For any actual playback request, use video_player so sound starts on and ORI "
        "can manage buffering, mute state and microphone handoff."
    ),''',
        label="route YouTube playback away from browser-only tool",
    )

    # Add an independent progress watchdog for the YouTube audio player.
    replace_once(
        source / "core" / "media_sync.py",
        '''@dataclass(frozen=True)
class SyncDecision:''',
        '''class PlaybackProgressWatchdog:
    """Detect a media transport that claims to play but stops advancing."""

    def __init__(self, stall_after_s: float = 8.0) -> None:
        self.stall_after_s = max(1.0, float(stall_after_s))
        self.last_position: int | None = None
        self.last_progress_at = 0.0

    def reset(self, *, now: float = 0.0, position: int | None = None) -> None:
        self.last_position = None if position is None else int(position)
        self.last_progress_at = float(now)

    def stalled(self, position: int, now: float, *, playing: bool) -> bool:
        current = int(position)
        moment = float(now)
        if not playing:
            self.reset(now=moment, position=current)
            return False
        if self.last_position is None or current != self.last_position:
            self.reset(now=moment, position=current)
            return False
        if self.last_progress_at <= 0.0:
            self.last_progress_at = moment
            return False
        return moment - self.last_progress_at >= self.stall_after_s


@dataclass(frozen=True)
class SyncDecision:''',
        label="media progress watchdog helper",
    )
    replace_once(source / "ui.py",
                 'from core.media_sync import SplitStreamSync',
                 'from core.media_sync import SplitStreamSync, PlaybackProgressWatchdog',
                 label="UI watchdog import")
    replace_once(
        source / "ui.py",
        '''        self._video_last_position = -1
        self._video_last_progress_t = time.monotonic()
        self._video_stall_since = 0.0
        self._video_cont = QWidget()''',
        '''        self._video_last_position = -1
        self._video_last_progress_t = time.monotonic()
        self._video_audio_progress = PlaybackProgressWatchdog(stall_after_s=8.0)
        self._video_stall_since = 0.0
        self._video_cont = QWidget()''',
        label="UI audio watchdog state",
    )
    replace_once(
        source / "ui.py",
        '''        self._video_last_position = -1
        self._video_last_progress_t = time.monotonic()
        self._video_stall_since = 0.0
        for p in (self._video_player, self._video_sound):''',
        '''        self._video_last_position = -1
        self._video_last_progress_t = time.monotonic()
        if hasattr(self, "_video_audio_progress"):
            self._video_audio_progress.reset(now=time.monotonic())
        self._video_stall_since = 0.0
        for p in (self._video_player, self._video_sound):''',
        label="UI reset watchdog",
    )
    replace_once(
        source / "ui.py",
        '''        self._video_last_position = -1
        self._video_last_progress_t = time.monotonic()
        self._video_stall_since = 0.0

        url = (QUrl.fromLocalFile(source) if Path(source).exists()''',
        '''        self._video_last_position = -1
        self._video_last_progress_t = time.monotonic()
        self._video_audio_progress.reset(now=time.monotonic())
        self._video_stall_since = 0.0

        url = (QUrl.fromLocalFile(source) if Path(source).exists()''',
        label="UI open watchdog",
    )
    replace_once(
        source / "ui.py",
        '''        if not (self._video_on and self._video_player):
            return
        try:
            if self._video_player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:''',
        '''        if not (self._video_on and self._video_player):
            return
        try:
            now = time.monotonic()
            # YouTube audio is carried by a second QMediaPlayer. The old watchdog
            # watched only the picture position, so a frozen soundtrack could
            # remain silent while the video kept advancing.
            if self._video_split and self._video_sound:
                audio_playing = (
                    self._video_sound.playbackState()
                    == QMediaPlayer.PlaybackState.PlayingState
                )
                audio_position = int(self._video_sound.position())
                if self._video_audio_progress.stalled(
                    audio_position, now, playing=audio_playing
                ):
                    log_diagnostic(
                        f"Audio watchdog: split soundtrack stopped advancing at "
                        f"{audio_position} ms; rebuilding the media stream."
                    )
                    self.write_log(
                        "SYS: Media audio stopped responding. Recovering the soundtrack…"
                    )
                    self._recover_video_stream(
                        audio_position, force_reopen=bool(self._video_network_source)
                    )
                    self._video_audio_progress.reset(
                        now=time.monotonic(), position=audio_position
                    )
                    return
            if self._video_player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:''',
        label="UI audio progress recovery",
    )
    replace_once(
        source / "ui.py",
        '''            position = int(self._video_player.position())
            now = time.monotonic()''',
        '''            position = int(self._video_player.position())''',
        label="avoid duplicate watchdog clock read",
    )

    # Prevent the model from issuing clicks against an unknown cursor position.
    replace_once(
        source / "actions" / "computer_control.py",
        '''def _click(x=None, y=None, button: str = "left", clicks: int = 1) -> str:
    _require_pyautogui()
    if x is not None and y is not None:
        pyautogui.click(x, y, button=button, clicks=clicks)
        return f"{'Double-c' if clicks == 2 else 'C'}licked ({x}, {y}) [{button}]"
    pyautogui.click(button=button, clicks=clicks)
    return f"Clicked at current position [{button}]"''',
        '''def _click(x=None, y=None, button: str = "left", clicks: int = 1) -> str:
    """Click only a known screen coordinate; never guess the current pointer."""
    if x is None or y is None:
        return (
            "No click was performed because screen coordinates are missing. "
            "Use screen_click with a description of the visible button or element, "
            "or take a screenshot and provide verified x/y coordinates."
        )
    _require_pyautogui()
    width, height = pyautogui.size()
    px, py = int(x), int(y)
    if not (0 <= px < width and 0 <= py < height):
        return f"No click was performed: ({px}, {py}) is outside the {width}x{height} screen."
    pyautogui.click(px, py, button=button, clicks=clicks)
    return f"{'Double-c' if clicks == 2 else 'C'}licked ({px}, {py}) [{button}]"''',
        label="safe coordinate mouse clicks",
    )
    replace_once(
        source / "actions" / "computer_control.py",
        '''    "description": "Direct computer control. For type/smart_type/paste, use only literal user-supplied or explicitly confirmed text; never guess or rewrite speech. These actions report keyboard input sent, not verified destination contents. Ask the user to repeat or confirm unclear dictated text before calling them. Window closing is graceful and post-close verified.",''',
        '''    "description": (
        "Direct mouse, keyboard and visible-screen control for the user's computer. "
        "For an on-screen button or UI element, use screen_click and describe the "
        "visible target; it captures the screen, finds the target and clicks it. "
        "For exact coordinates, use click/double_click/right_click only when x AND y "
        "are known from a fresh screenshot. Never click at an unspecified/current "
        "pointer position. Use screenshot or screen_find before guessing coordinates. "
        "Use hotkey/press for keyboard shortcuts and focus_window before interacting "
        "with a specific app. For type/smart_type/paste, use only literal user-supplied "
        "or explicitly confirmed text; preserve it exactly. Keyboard/mouse input sent "
        "does not prove the app accepted it; verify the resulting state when possible. "
        "Window closing is graceful and post-close verified."
    ),''',
        label="computer tool guidance",
    )
    replace_once(
        source / "actions" / "computer_control.py",
        '''"description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | close_window | screen_find | screen_click | random_data | user_data"''',
        '''"description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | close_window | screen_find | screen_click | random_data | user_data. Use screen_click(description) for visible UI elements; click requires exact x/y."''',
        label="computer tool action guidance",
    )
    replace_once(source / "actions" / "computer_control.py",
                 '"description": "X coordinate"',
                 '"description": "Exact X pixel from the latest screenshot; required together with y for click actions."',
                 label="mouse x description")
    replace_once(source / "actions" / "computer_control.py",
                 '"description": "Y coordinate"',
                 '"description": "Exact Y pixel from the latest screenshot; required together with x for click actions."',
                 label="mouse y description")

    # Resolve Chrome from its actual Windows install location and support ChatGPT.
    replace_once(
        source / "actions" / "open_app.py",
        '''    "google chrome":      {"Windows": "chrome",                  "Darwin": "Google Chrome",        "Linux": "google-chrome"},''',
        '''    "google chrome":      {"Windows": "chrome",                  "Darwin": "Google Chrome",        "Linux": "google-chrome"},
    "chatgpt":             {"Windows": "https://chatgpt.com",        "Darwin": "https://chatgpt.com",  "Linux": "https://chatgpt.com"},
    "chat gpt":           {"Windows": "https://chatgpt.com",        "Darwin": "https://chatgpt.com",  "Linux": "https://chatgpt.com"},''',
        label="ChatGPT aliases",
    )
    replace_once(
        source / "actions" / "open_app.py",
        '''def _launch_windows(app_name: str) -> bool:
    executable = shutil.which(app_name) or shutil.which(app_name.split(".")[0])''',
        '''def _windows_chrome_executable() -> str | None:
    """Find Chrome from common Windows install paths and the App Paths registry."""
    import os
    from pathlib import Path

    candidates = [
        Path(os.environ.get("PROGRAMFILES", r"C:\\Program Files"))
        / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\\Program Files (x86)"))
        / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    try:
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                try:
                    key = winreg.OpenKey(
                        hive, r"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\chrome.exe",
                        0, winreg.KEY_READ | view,
                    )
                    with key:
                        value, _kind = winreg.QueryValueEx(key, "")
                    if value and Path(value).is_file():
                        return str(value)
                except OSError:
                    continue
    except Exception:
        pass
    return None


def _launch_windows(app_name: str) -> bool:
    if app_name.lower().startswith(("https://", "http://")):
        try:
            import os
            os.startfile(app_name)
            return True
        except Exception as exc:
            print(f"[open_app] URL launch failed: {exc}")
            return False

    if app_name.lower() in {"chrome", "chrome.exe", "google chrome"}:
        chrome = _windows_chrome_executable()
        if chrome:
            try:
                subprocess.Popen(
                    [chrome], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                if _wait_for_windows_app("chrome.exe", timeout=12.0):
                    return True
            except Exception as exc:
                print(f"[open_app] Chrome path launch failed: {exc}")

    executable = shutil.which(app_name) or shutil.which(app_name.split(".")[0])''',
        label="Chrome direct launcher",
    )
    replace_once(
        source / "actions" / "open_app.py",
        '''    "description": "Opens any application on the computer. Use this whenever the user asks to open, launch, or start any app, website, or program. Always call this tool — never just say you opened it.",''',
        '''    "description": (
        "Opens an application, website or program on the computer. Always call this "
        "tool when asked to open or launch something, then report only the verified "
        "result. Use app_name='Chrome' to launch installed Google Chrome (searched "
        "by common Windows install paths and App Paths registry), and "
        "app_name='ChatGPT' to open https://chatgpt.com in the default browser. "
        "Do not interpret vague 'chat' as an app unless context clearly means ChatGPT."
    ),''',
        label="open_app instructions",
    )
    replace_once(
        source / "actions" / "open_app.py",
        '''"description": "Exact name of the application (e.g. 'WhatsApp', 'Chrome', 'Spotify')"''',
        '''"description": "Application or website to open, e.g. 'Chrome', 'ChatGPT', 'WhatsApp' or 'Spotify'. Use 'ChatGPT' for https://chatgpt.com."''',
        label="open_app parameter guidance",
    )

    # Regression tests for song/media tool routing.
    routing_test = source / "tests" / "test_media_routing.py"
    routing_test.write_text(
        """from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_video_player_is_the_route_for_music_and_song_requests():
    declaration = (ROOT / "actions" / "video_player.py").read_text(encoding="utf-8")
    assert "Plays MUSIC, SONGS and VIDEOS" in declaration
    assert "PLAY or HEAR music/songs" in declaration
    assert "Do NOT use 'youtube_video' for playback" in declaration


def test_browser_only_youtube_tool_is_not_described_as_the_playback_route():
    declaration = (ROOT / "actions" / "youtube_video.py").read_text(encoding="utf-8")
    assert "Do NOT use this tool to play music, songs or videos" in declaration
    assert "use video_player" in declaration
""",
        encoding="utf-8",
    )

    with routing_test.open("a", encoding="utf-8") as handle:
        handle.write('''


def test_legacy_youtube_play_action_delegates_to_managed_media_player(monkeypatch):
    from actions import youtube_video, video_player as video_player_module

    calls = []
    monkeypatch.setattr(
        video_player_module,
        "video_player",
        lambda params, player=None: calls.append((params, player)) or "status=opening",
    )
    fake_player = object()
    result = youtube_video._handle_play({"query": "Arijit Singh songs"}, fake_player)

    assert result == "status=opening"
    assert calls == [({"action": "play", "source": "Arijit Singh songs"}, fake_player)]
''')

    # Regression tests for the new behaviours.
    replace_once(
        source / "tests" / "test_video_player.py",
        'self.assertEqual(out, "Playing song.mp4 on the display, muted. Qt playback was confirmed.")',
        'self.assertEqual(out, "Playing song.mp4 with sound on. Qt playback was confirmed.")',
        label="local media expected result",
    )
    replace_once(source / "tests" / "test_video_player.py",
                 'self.assertTrue(player.shown[0]["muted"])',
                 'self.assertFalse(player.shown[0]["muted"])',
                 label="local media audible by default")
    replace_once(
        source / "tests" / "test_video_player.py",
        'self.assertEqual(out, "Playing that on the display, muted. Qt playback was confirmed.")',
        'self.assertEqual(out, "Playing that with sound on. Qt playback was confirmed.")',
        label="direct URL expected result",
    )
    replace_once(
        source / "tests" / "test_video_player.py",
        'self.assertEqual(player.shown[0]["source"], "https://example.com/test.mp4")',
        'self.assertEqual(player.shown[0]["source"], "https://example.com/test.mp4")\n        self.assertFalse(player.shown[0]["muted"])',
        label="direct URL audible by default",
    )

    tests = source / "tests" / "test_audio_stream.py"
    with tests.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write('''

def test_playback_watchdog_detects_a_frozen_audio_clock():
    from core.media_sync import PlaybackProgressWatchdog

    watch = PlaybackProgressWatchdog(stall_after_s=8.0)
    assert watch.stalled(100, 1.0, playing=True) is False
    assert watch.stalled(100, 8.9, playing=True) is False
    assert watch.stalled(100, 9.1, playing=True) is True


def test_playback_watchdog_resets_after_progress_or_pause():
    from core.media_sync import PlaybackProgressWatchdog

    watch = PlaybackProgressWatchdog(stall_after_s=8.0)
    watch.stalled(100, 1.0, playing=True)
    assert watch.stalled(200, 7.0, playing=True) is False
    assert watch.stalled(200, 14.0, playing=False) is False
    assert watch.stalled(200, 15.0, playing=True) is False


def test_voice_leveler_smooths_loudness_and_limits_peaks():
    import numpy as np
    from core.voice_leveler import VoiceLeveler

    leveler = VoiceLeveler(sample_rate=24_000)
    t = np.arange(4800, dtype=np.float32)
    quiet = (np.sin(2 * np.pi * 440 * t / 24_000) * 1200).astype("<i2")
    loud = (np.sin(2 * np.pi * 440 * t / 24_000) * 18_000).astype("<i2")
    quiet_out = np.frombuffer(leveler.process(quiet.tobytes()), dtype="<i2")
    gain_after_quiet = leveler.gain
    loud_out = np.frombuffer(leveler.process(loud.tobytes()), dtype="<i2")

    quiet_rms = float(np.sqrt(np.mean(quiet.astype(np.float32) ** 2)))
    loud_rms = float(np.sqrt(np.mean(loud.astype(np.float32) ** 2)))
    quiet_out_rms = float(np.sqrt(np.mean(quiet_out.astype(np.float32) ** 2)))
    loud_out_rms = float(np.sqrt(np.mean(loud_out.astype(np.float32) ** 2)))

    assert gain_after_quiet > 1.0
    assert quiet_out_rms > quiet_rms
    assert loud_out_rms < loud_rms
    assert int(np.max(np.abs(loud_out.astype(np.int32)))) <= 30_000


def test_voice_leveler_does_not_amplify_silence():
    import numpy as np
    from core.voice_leveler import VoiceLeveler

    leveler = VoiceLeveler(sample_rate=24_000)
    silence = np.zeros(2400, dtype="<i2").tobytes()
    leveler.gain = 1.25
    assert leveler.process(silence) == silence
    assert leveler.gain == 1.25
''')

    tests = source / "tests" / "test_computer_control_window.py"
    with tests.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write('''

def test_click_requires_coordinates_and_never_clicks_current_pointer(monkeypatch):
    calls = []
    monkeypatch.setattr(control, "_PYAUTOGUI", True)
    monkeypatch.setattr(control, "pyautogui", SimpleNamespace(
        size=lambda: (1920, 1080),
        click=lambda *args, **kwargs: calls.append((args, kwargs)),
    ))

    result = control._click()

    assert "coordinates are missing" in result
    assert calls == []


def test_click_rejects_coordinates_outside_screen(monkeypatch):
    calls = []
    monkeypatch.setattr(control, "_PYAUTOGUI", True)
    monkeypatch.setattr(control, "pyautogui", SimpleNamespace(
        size=lambda: (1920, 1080),
        click=lambda *args, **kwargs: calls.append((args, kwargs)),
    ))

    result = control._click(3000, 500)

    assert "outside" in result
    assert calls == []


def test_chatgpt_alias_resolves_to_official_website(monkeypatch):
    monkeypatch.setattr(open_app, "_SYSTEM", "Windows")
    assert open_app._normalize("ChatGPT") == "https://chatgpt.com"
    assert open_app._normalize("chat gpt") == "https://chatgpt.com"
''')

    # The source test still hard-codes an obsolete installer version in its CI contract.
    # Keep the assertion tied to the installer naming scheme, not one historical release.
    replace_once(
        source / "tests" / "test_installer_contract.py",
        'assert "ORI-Setup-3.6.0.exe" in workflow',
        'assert "ORI-Setup-" in workflow',
        label="refresh installer workflow contract",
    )

    print(f"Applied ORI 3.6.6 quality fixes to {source}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    patch(args.source.resolve())


if __name__ == "__main__":
    main()
