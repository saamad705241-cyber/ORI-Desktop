import actions.computer_control as cc


class FakeClipboard:
    def __init__(self):
        self.value = "previous"
        self.copied = []

    def paste(self):
        return self.value

    def copy(self, value):
        self.value = value
        self.copied.append(value)


class FakePyAuto:
    def __init__(self, cancel_after=2):
        self.hotkeys = []
        self.writes = []
        self.cancel_after = cancel_after

    def hotkey(self, *keys, **kwargs):
        self.hotkeys.append(keys)
        if keys == ("ctrl", "v") and self.hotkeys.count(("ctrl", "v")) >= self.cancel_after:
            cc._ACTION_CANCEL.set()

    def write(self, text, interval=0, **kwargs):
        self.writes.append(text)
        if len(self.writes) >= self.cancel_after:
            cc._ACTION_CANCEL.set()

    def press(self, *_args, **_kwargs):
        pass


def _patch_clipboard(monkeypatch, fake_auto):
    clip = FakeClipboard()
    monkeypatch.setattr(cc, "_PYAUTOGUI", True)
    monkeypatch.setattr(cc, "pyautogui", fake_auto, raising=False)
    monkeypatch.setattr(cc, "_PYPERCLIP", True)
    monkeypatch.setattr(cc, "pyperclip", clip, raising=False)
    return clip


def test_chunked_unicode_typing_stops_between_batches_and_restores_clipboard(monkeypatch):
    fake_auto = FakePyAuto(cancel_after=2)
    clip = _patch_clipboard(monkeypatch, fake_auto)
    cc._ACTION_CANCEL.clear()

    sent, cancelled = cc._type_chunks("नमस्ते " * 100, chunk_size=4)

    assert cancelled is True
    assert len(clip.copied[:-1]) == 2
    assert sent == sum(len(piece) for piece in clip.copied[:-1])
    assert fake_auto.hotkeys.count(("ctrl", "v")) == 2
    assert clip.value == "previous"


def test_ascii_typing_stops_between_short_batches(monkeypatch):
    fake_auto = FakePyAuto(cancel_after=2)
    monkeypatch.setattr(cc, "_PYAUTOGUI", True)
    monkeypatch.setattr(cc, "pyautogui", fake_auto, raising=False)
    monkeypatch.setattr(cc, "_PYPERCLIP", False)
    cc._ACTION_CANCEL.clear()

    sent, cancelled = cc._type_chunks("A" * 100, chunk_size=6)

    assert cancelled is True
    assert sent == 12
    assert len(fake_auto.writes) == 2


def test_new_computer_action_clears_previous_cancel_event(monkeypatch):
    fake_auto = FakePyAuto(cancel_after=99)
    _patch_clipboard(monkeypatch, fake_auto)
    cc._ACTION_CANCEL.set()
    cc.clear_cancel_request()  # the dispatcher clears it before starting a new call
    result = cc.computer_control({"action": "type", "text": "Hello"})
    assert "Keyboard input sent" in result
    assert "not read back" in result
    assert not cc._ACTION_CANCEL.is_set()


def test_unicode_grapheme_chunks_preserve_devanagari_and_wait_for_paste(monkeypatch):
    fake_auto = FakePyAuto(cancel_after=999)
    clip = _patch_clipboard(monkeypatch, fake_auto)
    cc._ACTION_CANCEL.clear()
    text = "नमस्ते, क्षमा कीजिए। यह ORI है।"
    sleep_calls = []
    monkeypatch.setattr(cc.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    sent, cancelled = cc._type_chunks(text, chunk_size=6)

    batches = clip.copied[:-1]  # the final clipboard write restores "previous"
    assert cancelled is False
    assert sent == len(text)
    assert "".join(batches) == text
    assert clip.value == "previous"
    assert len(sleep_calls) == len(batches)
    assert all(delay >= cc._CLIPBOARD_PASTE_SETTLE_SECONDS for delay in sleep_calls)

    expected_graphemes = cc._unicode_regex.findall(r"\X", text)
    actual_graphemes = [
        grapheme
        for batch in batches
        for grapheme in cc._unicode_regex.findall(r"\X", batch)
    ]
    assert actual_graphemes == expected_graphemes
