# Changelog

## 3.5.0 — 12 November 2026

- Added interruptible chunked keyboard text entry and live voice barge-in during assistant speech or long desktop actions.
- Added WebRTC VAD plus adaptive speaker-echo rejection; no biometric speaker identity is claimed.
- Added user-consented continuous screen watch at up to 1 FPS with visible access indicators.
- Added live MIC, SPK, SCREEN, KEYS, MOUSE, WEB, FILES, CAM, NET, SYSTEM and PHONE activity indicators.
- Added desktop overview and bounded, read-only Windows Update diagnostics.
- Added GitHub latest-release checks, SHA-256 verified downloads, Windows packaged update helper and CI/release workflows.
- Added Instagram profile shortcut and owner-configured repository setup helper.
- Kept analytics/user-count server integration deferred; no Firebase admin/user analytics controls were added to the end-user UI.

# ORI Changelog

## ORI 3.4 Remote callback hotfix — 12 November 2026

- Fixed the `JarvisUI.set_muted_from_remote` facade used when the phone dashboard starts.
- Kept remote microphone state queries and UI-thread-safe mute updates on `MainWindow`.
- Added regression tests for the dashboard-to-UI mute callback contract.

## ORI 3.4 — 12 November 2026

- Preserved the original PyQt desktop app, Gemini Live runtime, 64-band audio
  engine and original QR pairing flow.
- Added early dashboard startup status, explicit bind failures and `/health`.
- Added authenticated touchpad, allow-listed keyboard/media/system controls,
  adjustable pointer/scroll speed and PC volume control.
- Added a local WebSocket PC screen stream for the paired phone and retained
  one-shot PC screenshots.
- Added opt-in phone screen frame ingestion and an explicit Gemini visual
  analysis queue; frames are held in memory only.
- Added one-time Android companion pairing codes and native Android
  MediaProjection source under `android-companion/`.
- Added phone remote UI panels for Touchpad, PC Screen, Quick Controls and Phone
  Screen Share while keeping the desktop ORI interface unchanged.

## ORI 3.3 — 11 November 2026

- Original-based Settings and remote refresh, with existing source attribution.
