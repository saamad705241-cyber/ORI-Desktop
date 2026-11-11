# ORI 3.4.1 — Phone Remote Startup Hotfix

## Symptom
The Phone Remote settings panel reported:

`AttributeError: 'JarvisUI' object has no attribute 'set_muted_from_remote'`

The dashboard setup passes a callback from `main.py` through the public `JarvisUI`
facade. The method had been placed on `MainWindow` only, so the callback lookup failed
before the dashboard could start.

## Fix
- `MainWindow.set_muted_from_remote()` now queries current state when called with
  `None`, and emits the existing Qt signal when asked to change the mute state.
- `JarvisUI.set_muted_from_remote()` now forwards the call to its `MainWindow`.
- Added regression tests for the facade method and thread-safe signal behavior.

## Verification
- Python tests: 114 passed.
- Python source compilation: passed.
- The generated TLS certificate/key directory is intentionally excluded from this ZIP.
  ORI generates local certificates when the dashboard starts.

## Install
Extract this complete source package into a new folder, run `setup.bat`, then `run.bat`.
Do not copy an existing `config/certs` folder into the new installation.
