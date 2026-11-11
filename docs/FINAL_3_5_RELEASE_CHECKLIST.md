# ORI 3.5.0 final integration checklist

## Included in this source build

- Gemini Live session with current API input/output path.
- Explicit screen-watch start/stop tools. The watcher sends at most one image frame per second using the Gemini Live realtime video input.
- Live access indicators for microphone, speaker, screen, keyboard, mouse, browser, files, camera, network and system actions.
- WebRTC VAD + EchoGuard speech/echo barge-in gate.
- Cooperative cancellation for chunked computer text input.
- Desktop overview action and Windows Update read-only check/open action with bounded timeout.
- GitHub Releases checker, checksum-verifying downloader and packaged Windows updater helper.
- Instagram profile button in About, using the profile URL recorded in `ori_metadata.py`.
- CI, Gitleaks workflow, Windows release workflow and repository setup helper.

## Local automated verification

- `python -m pytest -q`
- `python -m compileall -q .`
- JSON/TOML parse checks
- JavaScript syntax checks for dashboard assets
- ZIP integrity and secret-file exclusion checks

## Still requires target-device verification

- Actual Gemini Live interruption behaviour with the user's microphone/speaker and room echo.
- Windows UI Automation, long text entry interruption and Windows Update COM search on Windows 11.
- Continuous screen-watch visual correctness, privacy indicator timing and Gemini video input quota.
- Phone remote over the user's actual private Wi-Fi, screen stream latency and file-transfer paths.
- PyInstaller one-folder build, code-signing/signing key setup and update replacement on a test VM.
- Public GitHub repository and release workflow. No repository owner/name is assumed or hard-coded.

Passing unit tests is not a substitute for those end-to-end tests. The UI must report capability failures honestly.
