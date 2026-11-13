from core import plugin_loader


def _registry(run_fn):
    record = plugin_loader.PluginRecord(
        name="sample_plugin",
        description="A test plugin",
        parameters={"type": "OBJECT", "properties": {}},
        run=run_fn,
        valid=True,
    )
    return plugin_loader.PluginRegistry(
        {"sample_plugin": record},
        logger=lambda _message: None,
    )


def test_plugin_empty_result_is_unverified_not_done(monkeypatch):
    monkeypatch.setattr(plugin_loader, "get_plugin_enabled", lambda _name: True)
    registry = _registry(lambda _params: None)

    result = registry.run("sample_plugin", {})

    assert "outcome is unverified" in result
    assert "Done." not in result


def test_plugin_whitespace_result_is_unverified(monkeypatch):
    monkeypatch.setattr(plugin_loader, "get_plugin_enabled", lambda _name: True)
    registry = _registry(lambda _params: "   ")

    result = registry.run("sample_plugin", {})

    assert "outcome is unverified" in result


def test_plugin_success_result_is_preserved(monkeypatch):
    monkeypatch.setattr(plugin_loader, "get_plugin_enabled", lambda _name: True)
    registry = _registry(lambda _params: "Verified result.")

    result = registry.run("sample_plugin", {})

    assert result == "Verified result."
