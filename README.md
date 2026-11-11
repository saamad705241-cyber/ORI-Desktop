# ORI 3.5.0 — Personal AI Desktop Assistant

ORI is a Windows-first, voice-first desktop assistant built around Google Gemini Live, a dynamic action registry, local memory, Windows/browser automation and an optional paired-phone dashboard. The main interface remains a minimal dark terminal with a thin green audio signal; capabilities are invoked through natural language rather than a visible feature dashboard.

## Windows quick start

1. Install Python 3.12 or 3.13 and the Python launcher.
2. Extract this project to a short, writable path such as `C:\ORI`.
3. Run `setup.bat` once. It creates `.venv` and installs the dependencies.
4. Run `run.bat`.
5. On first launch, choose Continue as Guest, set optional profile preferences and enter a Google AI Studio API key.

The normal setup intentionally skips Playwright's large browser binaries. If a browser automation workflow specifically needs them, run `scripts\install_browser_runtime.bat` once.

Get a Gemini API key from https://aistudio.google.com/app/apikey. Keep `config/api_keys.json` private.

## Current integrated capabilities

- Gemini Live voice conversation with microphone/speaker audio and 64-band spectrum.
- Voice barge-in: WebRTC VAD plus adaptive echo rejection can interrupt ORI while it is speaking. During long desktop actions, sustained speech can request cancellation.
- Cancellable, chunked text entry. Large typing actions check for cancellation between batches.
- Dynamic tool/action registry; Gemini chooses tools from the capabilities installed in the runtime rather than a hard-coded command phrase list.
- Single-frame desktop/camera analysis and explicit continuous screen watch at up to 1 frame per second while requested.
- Live access indicators for microphone, speaker, screen, keyboard, mouse, browser, files, camera, network and system operations.
- Desktop overview and bounded, read-only Windows Update diagnostics.
- Windows/browser/file/media actions where their dependencies and permissions are available.
- QR-paired phone dashboard on a trusted private LAN: touchpad, keyboard, media/volume, local file transfer, PC screen view and phone-screen frame intake for Gemini analysis.
- Local memory, profile preferences, CPU/RAM/temperature monitoring, and system status reporting.
- GitHub release checker and SHA-256 verified Windows package downloads. Automatic replacement is restricted to packaged one-folder Windows builds.

Features remain dependent on OS version, permissions, installed components, hardware drivers, Gemini availability and network access. An unavailable sensor or action is reported as unavailable; ORI must not claim success without a verified result.

## Interrupting ORI

- Use the interrupt button or `Esc` at any time.
- When voice interruption is enabled, speak a clear phrase while ORI is talking or executing a long task. Speech is gated by WebRTC VAD and EchoGuard to reduce false triggers from speaker echo and background noise.
- Voice barge-in is speech-vs-noise/echo detection, not biometric identification of a specific person.
- Long typing operations enter text in short batches and stop between batches when cancellation is requested.

## Continuous screen monitoring

Say that ORI should keep watching/monitoring your screen. ORI starts a background capture loop at no more than 1 FPS and streams frames to the active Gemini Live session. The SCREEN indicator stays visible until you say to stop. Frames are not saved to disk by the watcher. This consumes API/network usage and can expose anything visible on screen; only enable it when appropriate.

## Phone remote

1. Start ORI on a trusted private Wi-Fi network.
2. Open Settings → Phone Remote → Pair Phone.
3. Scan the one-time QR code with the phone camera.
4. The remote page opens in the phone browser. Use its touchpad, keyboard, media controls, file transfer and PC screen view.
5. Phone screen sharing uses the optional Android Screen Companion source in `android-companion/`; the browser alone cannot capture a full Android device screen on all browsers. Build and permission details are in `android-companion/README.md`.

ORI does not silently change a Windows network from Public to Private and does not open public internet ports. Use a trusted LAN only. Do not expose the remote dashboard directly to the public internet.

## Repository and updates

- Configure `github_repository` in your private `config/api_keys.json` as `OWNER/REPOSITORY` after creating the official GitHub repository.
- `.github/workflows/ci.yml` runs tests, source compilation, Ruff correctness checks and Gitleaks.
- Push a matching tag such as `v3.5.0` to trigger `.github/workflows/release.yml`.
- The release workflow publishes a Windows one-folder ZIP and a `.sha256` checksum asset.
- In Settings → About, Check for Updates reads the latest GitHub release. Downloaded packages must pass SHA-256 verification. Source/development installs are never overwritten automatically.

See `docs/RELEASE_AND_UPDATES.md` and `scripts/initialize_repository.bat`.

## Development checks

```cmd
python -m pytest -q
python -m ruff check --select F main.py ui.py core actions memory dashboard tests
```

Run `build_windows_exe.bat` to create a local one-folder package after dependencies are installed. Verify `dist\ORI\ORI.exe` on Windows before sharing it.

## Security and privacy

- Never commit `config/api_keys.json`, TLS private keys, pairing tokens, OAuth tokens, local memory, logs or personal files.
- Read-only Windows Update checks have a timeout; ORI does not install Windows updates or restart the PC from that tool.
- Destructive or externally consequential operations must require confirmation.
- Microphone, camera, screen and remote access must follow visible indicators and OS permissions.

## Licensing and attribution

This archive is based on the user-supplied ORI 3.1 project. Some inherited files are identified in the upstream notices as derivative of MARK LV by FatihMakes under CC BY-NC 4.0. The attribution and non-commercial conditions remain applicable to those portions. Read `LICENSE`, `ATTRIBUTION.md`, `UPSTREAM_MARK_LV_README.md` and `THIRD_PARTY_LICENSES.md` before redistribution. Commercial use requires separate permission or replacement of restricted portions with independently licensed implementations.
