# ORI 3.4 Build Notes

This build keeps the original ORI 3.1 PyQt application, Gemini Live session,
64-band audio display, settings shell and QR pairing architecture. It enhances
the remote dashboard rather than replacing the desktop app with a new framework.

## Remote additions

- Startup status and Uvicorn bind diagnostics; `/health` endpoint.
- Authenticated low-latency touchpad WebSocket with bounded relative movement,
  clicks, scrolling and allow-listed key/media/system actions.
- Authenticated PC screen WebSocket streaming JPEG frames over the local LAN.
- Authenticated phone screen frame ingestion and explicit Gemini visual-analysis
  queue in the existing Live session.
- One-time Android companion pairing code endpoint and native Android source.
- Per-phone action rate limiting and device revoke handling for companion tokens.

## Verification limitations

Automated Python, JavaScript syntax and package integrity checks are included in
`docs/ORI_3_4_VERIFICATION_REPORT.md`. This environment cannot run the Windows
PyQt6 desktop UI or an Android device. The Android companion source is therefore
not represented as a built or device-verified APK. Actual Windows QR/LAN,
Windows screen capture, Android MediaProjection and Gemini Live end-to-end tests
must be completed on the user's devices.
