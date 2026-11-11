from __future__ import annotations

import py_compile
from pathlib import Path


def main() -> int:
    roots = ("actions", "core", "dashboard", "memory", "plugins", "tests", "scripts")
    failures: list[tuple[str, str]] = []
    for root in roots:
        base = Path(root)
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            try:
                py_compile.compile(str(path), doraise=True)
            except Exception as exc:  # pragma: no cover - displayed in CI output
                failures.append((str(path), f"{type(exc).__name__}: {exc}"))
    for name in ("main.py", "ui.py", "ori_metadata.py", "setup.py"):
        path = Path(name)
        if path.exists():
            try:
                py_compile.compile(str(path), doraise=True)
            except Exception as exc:  # pragma: no cover
                failures.append((str(path), f"{type(exc).__name__}: {exc}"))
    if failures:
        for path, error in failures:
            print(f"{path}: {error}")
        return 1
    print("All Python source files compiled successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
