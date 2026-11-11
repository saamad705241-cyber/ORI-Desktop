from actions.desktop_overview import TOOL as DESKTOP_TOOL
from actions.windows_update import TOOL as UPDATE_TOOL


def test_desktop_overview_is_a_discoverable_action():
    assert DESKTOP_TOOL["name"] == "desktop_overview"
    assert callable(DESKTOP_TOOL["handler"])
    assert DESKTOP_TOOL["parameters"]["type"] == "OBJECT"


def test_windows_update_is_read_only_and_bounded():
    assert UPDATE_TOOL["name"] == "windows_update"
    assert callable(UPDATE_TOOL["handler"])
    description = UPDATE_TOOL["description"].lower()
    assert "timeout" in description
    assert "never installs" in description
