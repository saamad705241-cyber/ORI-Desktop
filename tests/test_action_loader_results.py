from core.action_loader import ActionRecord, ActionRegistry


def _registry(handler):
    record = ActionRecord(
        name="sample_action",
        handler=handler,
        valid=True,
    )
    return ActionRegistry({"sample_action": record}, logger=lambda _message: None)


def test_empty_handler_result_is_not_reported_as_success():
    result = _registry(lambda **_kwargs: None).run("sample_action", {})

    assert "unverified" in result.lower()
    assert "do not report" in result.lower()
    assert "Done." not in result


def test_whitespace_handler_result_is_not_reported_as_success():
    result = _registry(lambda **_kwargs: "  \n  ").run("sample_action", {})

    assert "unverified" in result.lower()
    assert "do not report" in result.lower()


def test_real_handler_message_is_preserved():
    expected = "Closed Notepad and verified that its process exited."
    result = _registry(lambda **_kwargs: expected).run("sample_action", {})

    assert result == expected


def test_handler_exception_is_reported_as_failure():
    def fail(**_kwargs):
        raise RuntimeError("simulated failure")

    result = _registry(fail).run("sample_action", {})

    assert "failed" in result.lower()
    assert "simulated failure" in result
