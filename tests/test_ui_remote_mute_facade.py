"""Regression coverage for the UI facade used by the phone dashboard."""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def _extract_method(class_name: str, method_name: str):
    tree = ast.parse((ROOT / "ui.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name == method_name:
                    module = ast.Module(body=[child], type_ignores=[])
                    namespace = {}
                    exec(compile(ast.fix_missing_locations(module), "ui.py", "exec"), namespace)
                    return namespace[method_name]
    raise AssertionError(f"{class_name}.{method_name} is missing")


def test_main_window_remote_mute_is_thread_safe_and_queryable():
    method = _extract_method("MainWindow", "set_muted_from_remote")
    emitted = []
    fake = SimpleNamespace(
        _muted=False,
        _remote_mute_sig=SimpleNamespace(emit=lambda value: emitted.append(value)),
    )

    assert method(fake, None) is False
    assert method(fake, True) is True
    assert method(fake, False) is False
    assert emitted == [True, False]


def test_jarvis_ui_facade_exposes_remote_mute_callback():
    method = _extract_method("JarvisUI", "set_muted_from_remote")
    calls = []
    fake_window = SimpleNamespace(
        set_muted_from_remote=lambda value: calls.append(value) or bool(value)
    )
    fake_ui = SimpleNamespace(_win=fake_window)

    assert method(fake_ui, True) is True
    assert calls == [True]
