# Contributing to ORI

1. Read `LICENSE`, `ATTRIBUTION.md` and `UPSTREAM_MARK_LV_README.md` before making or distributing changes.
2. Do not commit `config/api_keys.json`, TLS private keys, pairing tokens, local memory, user files or logs.
3. Use Python 3.12 or 3.13 for the supported Windows development path.
4. Run `python -m pytest -q` and `python -m ruff check --select F main.py ui.py core actions memory dashboard tests` before opening a PR.
5. Keep desktop actions permission-aware and cancellable where they can run for more than a moment.
6. Do not claim an action succeeded unless its real result verifies it.
7. Keep the main ORI interface minimal; capabilities are discovered through natural language rather than feature dashboards.

By contributing, you confirm that you have the rights needed to submit your changes and understand the project's current third-party licensing obligations.
