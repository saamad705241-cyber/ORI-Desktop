# ORI 3.2 — Verification Report

## Source basis
This build is based on the user-supplied `ORI_3_1_remote_fixed_v2` archive. The original PyQt desktop application, main runtime, action modules, browser integration, memory modules, dashboard, assets, tests and license notices are retained. The earlier Tauri 0.2.x experiment is not the base for this package.

## Changes in this build
- First-run flow: Continue (Coming Soon) and Continue as Guest.
- Guest profile: preferred name, language and conversation style.
- Google AI Studio key validation uses the Gemini Models list endpoint and sends the key in the `x-goog-api-key` header. No model picker is exposed; ORI chooses compatible candidates automatically.
- Key verification runs in a background thread with a bounded timeout and does not block the UI.
- Settings simplified to AI key, profile/voice, audio devices, interface, voice automation, system/weather, system display, optional integrations, About/Updates, Terms and phone remote.
- Removed the Firebase Web API / sign-in configuration, browser settings card, privacy dashboard, diagnostic-copy controls, Developer settings card and Restricted Modes settings card from user-facing Settings.
- MUTE MIC / UNMUTE MIC button labels; STOP VOICE remains a separate interruption action.
- Top-bar CPU/RAM/temperature chips support values, compact sparkline graphs or both.
- The 64-band waveform remains driven by actual PCM; a very low-amplitude ambient trace keeps the HUD visually alive at silence.
- Phone dashboard adds authenticated PC microphone mute/unmute control.
- Windows firewall setup no longer changes a Public network profile to Private. A rule is offered only on a trusted Private network and is scoped to the local subnet.
- Machine-specific remote TLS certificates are generated locally; no private certificate key is distributed in the ZIP.
- Added beginner-friendly `setup.bat` and `run.bat` entry points.

## Automated checks run in this build environment
- Python test suite: **90 passed** (81 tests from the supplied archive plus 9 added regression tests).
- Python bytecode compilation: passed.
- Dashboard inline JavaScript syntax (`node --check`): passed.
- All JSON files: parsed successfully.
- Project TOML files: parsed successfully where present.
- ZIP archive integrity: verified after packaging.

## Not independently verified here
This execution environment does not provide Windows, PyQt6 desktop rendering, Windows UI Automation, a physical microphone/speaker, a real Google AI Studio API key, or a paired Android/iOS browser. Therefore the following still require end-to-end verification on the target Windows PC:
- PyQt desktop launch and first-run wizard rendering.
- Real Gemini Live audio session and actual spoken response.
- Specific Windows actions and browser session/tab behavior.
- Phone QR pairing over the user's trusted Wi-Fi and PC microphone mute from phone.
- Hardware temperature sensor discovery.
- Windows startup integration and any administrator/UAC prompts.

The setup scripts perform installation and tests on the target machine. Do not treat a green test suite as proof that third-party credentials, microphone hardware, Windows permissions or remote networking are configured.

## License
The original archive contains a CC BY-NC 4.0 license and identifies source derived from MARK LV by FatihMakes. The license and attribution notices are retained. Review `LICENSE`, `UPSTREAM_MARK_LV_README.md`, `THIRD_PARTY_LICENSES.md` and `ATTRIBUTION.md` before publication or redistribution.
