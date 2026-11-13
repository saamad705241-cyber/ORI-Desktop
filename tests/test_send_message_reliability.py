from actions import send_message


def test_desktop_message_fallback_refuses_blind_keyboard_delivery(monkeypatch):
    called = []
    monkeypatch.setattr(send_message, "_open_app", lambda *args: called.append("open"))
    monkeypatch.setattr(send_message, "_search_in_app", lambda *args: called.append("search"))

    result = send_message._desktop_send("Telegram", "Alex", "Hello")

    assert "No verified message-delivery adapter" in result
    assert "No message was sent" in result
    assert called == []


def test_instagram_and_messenger_are_not_reported_sent_without_verified_adapter():
    instagram = send_message._send_instagram("Alex", "Hello")
    messenger = send_message._send_messenger("Alex", "Hello")

    assert "No message was sent" in instagram
    assert "No message was sent" in messenger
    assert "verified delivery adapter" in instagram
    assert "verified delivery adapter" in messenger


def test_send_message_does_not_require_pyautogui_for_verified_adapter(monkeypatch):
    monkeypatch.setattr(send_message, "_PYAUTOGUI", False)
    monkeypatch.setattr(send_message, "_resolve_platform", lambda _platform: lambda _r, _m: "Message sent via verified transport.")

    result = send_message.send_message({
        "receiver": "Alex",
        "message_text": "Hello",
        "platform": "WhatsApp",
    })

    assert result == "Message sent via verified transport."


def test_whatsapp_missing_verified_driver_never_falls_back_to_keyboard(monkeypatch):
    monkeypatch.setattr(send_message, "_PYAUTOGUI", True)
    result = send_message._send_whatsapp("Alex", "Hello")

    assert "Verified WhatsApp delivery is unavailable" in result
    assert "No message was sent" in result
