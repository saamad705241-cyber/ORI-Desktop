from dashboard.server import DashboardServer


def test_dashboard_can_publish_access_activity_to_desktop_ui():
    server = object.__new__(DashboardServer)
    events = []
    server._access_callback = None
    server.set_access_callback(lambda name, active: events.append((name, active)))
    server._notify_access("keyboard", True)
    server._notify_access("keyboard", False)
    assert events == [("keyboard", True), ("keyboard", False)]


def test_dashboard_access_callback_failure_does_not_crash_remote():
    server = object.__new__(DashboardServer)
    server._access_callback = lambda *_args: (_ for _ in ()).throw(RuntimeError("ui gone"))
    server._notify_access("screen", True)
