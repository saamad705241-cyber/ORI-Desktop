# ORI Changelog

## 3.6.2 (14 November 2026)

- Require the update helper to verify the exact target version, Windows uninstall registration, startup-token PID, executable path and reported application version before confirming an update.
- Allow up to 90 seconds for startup and monitor the relaunched process for 15 seconds before reporting success.
- Stop an unverified new process before rollback, restore the previous program files on failure, and show the failure reason plus diagnostic log path.
- Pass the expected target version from the downloaded release metadata through the Settings update action and the Windows helper.
- Add Windows CI checks for the version handshake and target-version mismatch handling.

## 3.6.1 (14 November 2026)

- Restore sharp YouTube playback by selecting the highest available stream up to 1080p instead of imposing the previous 720p ceiling.
- Prefer broadly supported H.264/AVC and MP4 formats when resolution is equal, and use a single combined stream when it does not reduce picture quality.
- Give Qt multimedia players and audio outputs explicit window ownership to make stream teardown and replacement safer.
- Record Qt multimedia failures and uncaught Python/thread exceptions in `%LOCALAPPDATA%\\ORI\\logs\\ori-crash.log` for actionable diagnosis.
- Extend Windows package CI to exercise an in-place update from the published v3.6.0 Setup to the new installer, including startup verification and user-data preservation.

## 3.6.0 (14 November 2026)

- Add a per-user Windows Setup installer that bundles the application runtime and dependencies, creates Start Menu and optional Desktop shortcuts, and registers a Windows uninstaller.
- Move API credentials, preferences, long-term memory and user-created data out of program files so upgrades and uninstall preserve them; migrate existing portable config and memory without overwriting newer user data.
- Split in-app updates into explicit Check for Updates, Download Update and Install Update actions. Downloaded Setup executables are SHA-256 verified and are never installed until the user confirms.
- Replace ZIP file-copy updates with a detached Setup helper that backs up program files, installs in place, verifies the updated application's startup marker, and restores the previous program if installation or startup fails.
- Add a Settings uninstall action with a clear personal-data retention notice.
- Add bounded PCM jitter buffering, safe mic-queue overflow handling and PortAudio error recovery for Gemini Live voice output.
- Reduce split-stream video/audio resynchronization seeks to prevent repeated soundtrack interruptions.



## 3.5.4 (14 November 2026)

- Fix Windows clipboard timing so successive text batches are not pasted before the target application consumes the prior clipboard payload.
- Preserve Devanagari conjuncts and Unicode combining marks by splitting only at grapheme boundaries.
- Increase the normal typing batch size to reduce clipboard handoffs.
- Allow natural Hinglish code-switching while preserving Roman Hindi, Devanagari and supplied English wording in exact-text actions.
- Add regression tests for clipboard settling, Indic grapheme boundaries and Hinglish prompt behavior.

## 3.5.2 (13 November 2026)

- Fix the Windows self-update handoff so a detached installer logs progress, waits for ORI to exit with a timeout, copies staged files using source-relative user-data exclusions, verifies the installed executable SHA-256, and restarts ORI.
- Back up the previous program files and restore/restart the previous build if copying, verification or immediate startup fails.
- Add regression tests for installer launch, expected paths, missing staged executables and helper-script safeguards.

## 3.5.1 (13 November 2026)

- Read CPU package/Tctl/Tdie temperatures from LibreHardwareMonitor 0.9.6 through its loopback JSON endpoint, and share the same sensor reader between the top bar and hardware inventory.
- Add first-launch Windows device-location consent, local coordinate storage, area lookup and current weather.
- Add microphone mute/unmute and stop-voice icons.
- Update the Windows package to include PyWinRT location support and the new SVG assets.

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
