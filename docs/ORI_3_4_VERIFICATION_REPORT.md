# ORI 3.4 Verification Report

## Automated checks run in the build environment

- Python test suite: **112 passed**.
- Python bytecode compilation: all `.py` sources passed.
- Inline JavaScript syntax: passed with Node `--check`.
- JSON and TOML parsing: passed.
- Dashboard API tests: health, auth, one-time QR flow, phone frame ingestion,
  analyze queue, companion pairing/replay rejection, remote action auth and
  actual Uvicorn bind/readiness transition.
- ZIP integrity: checked after packaging.

## Not verified in this environment

- PyQt6 Windows GUI rendering, actual Windows mouse/keyboard injection and
  multi-monitor capture.
- Real Windows Firewall prompt and phone-to-PC LAN path.
- Real Gemini Live visual response using a user's API key.
- Android Studio/Gradle build and MediaProjection behavior on a physical phone.

The Android companion source is provided but there is no compiled APK in this
package. Use `android-companion/README.md` for setup and certificate trust.
