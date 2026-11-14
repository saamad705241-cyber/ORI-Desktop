# ORI Changelog

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

