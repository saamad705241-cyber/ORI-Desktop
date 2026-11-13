from core import confirm


class ImmediateThread:
    def __init__(self, target, **_kwargs):
        self.target = target

    def start(self):
        self.target()


def _run_confirmed(monkeypatch, result):
    messages = []
    monkeypatch.setattr(confirm.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(confirm.time, "monotonic", lambda: 10.0)
    confirm.bind(
        show=lambda *_args: None,
        hide=lambda: None,
        log=messages.append,
    )
    pending = confirm.request(
        key="test",
        title="Test action",
        detail="Confirm test",
        run=lambda: result,
    )
    assert "[CONFIRMATION_PENDING]" in pending
    confirm.resolve(True)
    return messages


def test_confirmed_action_with_empty_result_is_not_logged_as_done(monkeypatch):
    messages = _run_confirmed(monkeypatch, None)

    assert any("Outcome is unverified" in message for message in messages)
    assert not any("Done." in message for message in messages)


def test_confirmed_action_records_neutral_result_message(monkeypatch):
    messages = _run_confirmed(monkeypatch, "Restart request was rejected.")

    assert any("Action result: Restart request was rejected." in message for message in messages)
    assert not any("Confirmed — Test action." in message for message in messages)
