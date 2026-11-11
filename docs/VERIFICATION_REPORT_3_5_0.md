# ORI 3.5.0 verification report

Environment used for this build check: Linux x86_64, Python 3.13.5. The target product remains Windows-first.

## Passed

- Python automated tests: **138 passed**.
- Python source compile check: all source files compiled.
- JavaScript syntax: all dashboard JavaScript files passed `node --check`.
- JSON/TOML validation: passed.
- GitHub workflow YAML parse: passed.
- Update archive traversal guard and SHA-256 download verification tests: passed.
- Interruptible typing cancellation, VAD gate, echo-guard reset and access-callback tests: passed.

## Not run in this environment

- Ruff executable was unavailable because package registry DNS was unavailable. CI is configured to run Ruff's correctness checks.
- PyQt6 desktop window rendering, Windows UI Automation, Windows Update COM query, real microphone/speaker, Gemini Live API, Wi-Fi pairing and Android Screen Companion APK were not end-to-end tested on a Windows device here.
- PyInstaller Windows build, signed executable, and update installation/restart were not executed here.

Do not interpret unit-test success as confirmation of those device/service integrations. The app reports sensor, API, permissions and service failures rather than claiming those checks passed.
