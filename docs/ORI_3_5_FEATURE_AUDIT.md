# ORI 3.5.2 Feature Audit

**Purpose:** a conservative engineering inventory before producing the public Windows installer.
This is a source-and-test audit, not a claim that every capability has passed a live Windows test. Settings layout, shared sensor resolution, single-action updater sequencing and initial close/open verification safeguards are now present in the feature branch; they remain unmerged and must pass the latest CI plus target-Windows smoke tests.

## Evidence labels

- **Automated coverage:** a test exists and runs in CI for the stated behavior. This does not prove the full live feature.
- **Implemented / manual verification required:** code and UI are present, but real hardware, account, network, or interaction testing is still required.
- **Partial:** only part of the requested workflow is implemented or the available tests cover only a narrow path.
- **Not implemented / not verified:** the repository does not currently establish a complete working feature.

## Core application

| Area | Current evidence | Audit state | Release gate |
|---|---|---|---|
| Windows desktop UI and waveform | PyQt UI, HUD waveform, metrics header | Implemented / manual verification required | Startup, resizing, DPI scaling, shutdown |
| First-run setup and API key | Config manager, key validation and onboarding tests | Automated coverage for validation; live API required | Fresh profile, invalid key, network outage |
| Text chat and Gemini Live voice | Live client, audio capture/output, prompt and conversation pipeline | Implemented / manual verification required | Microphone, speaker, cloud connection and repeated sessions |
| Audio spectrum and voice interruption | Spectrum, VAD, EchoGuard and interruptible typing tests | Automated coverage for narrow components | Real mic/speaker, echo, barge-in and stop behavior |
| User profile, preferences and local memory | Config and memory modules with persistence tests | Partial / manual verification required | Save, restart, migration and data isolation |
| Theme and appearance controls | Palette and theme modules | Implemented / manual verification required | Change accent, restart, all screen sizes |

## Desktop and productivity actions

| Area | Source modules | Audit state | Release gate |
|---|---|---|---|
| App launch and computer input | `open_app.py`, `computer_control.py` | Initial reliability safeguards and regression tests added; full action audit and real Windows validation still required | Open-process/window check, graceful window close, unsaved-change dialog, focus, type, click, hotkey, timeout and postcondition |
| Browser automation | `browser_control.py` | Implemented / manual verification required | Supported browser, login state, timeout and permission behavior |
| File operations and document understanding | `file_controller.py`, `file_processor.py` | Implemented / manual verification required | Copy/move, safe delete, PDF/DOCX/XLSX and large files |
| Desktop overview and screen analysis | `desktop_overview.py`, `screen_processor.py` | Implemented / manual verification required | Capture permission, monitor selection and privacy indicator |
| Coding assistance | `code_helper.py`, `dev_agent.py` | Partial | Read/write boundaries, project context and user approval |
| Web search and research | `web_search.py` | Partial / model and network dependent | Current sources, citations, failure handling |
| Media playback and YouTube | `video_player.py`, `youtube_video.py` | Partial / manual verification required | Local file, URL, YouTube resolution and cancellation |
| Reminders and proactive checks | `reminder.py`, `proactive.py`, `background_monitor.py` | Partial | Persistence, schedule timing, missed events and duplicate suppression |
| Messaging/email integrations | `send_message.py` plus optional OAuth/plugins | Partial / requires account configuration | OAuth, recipient confirmation and end-to-end send |
| Travel/flight lookup | `flight_finder.py` | Partial / network dependent | Live route coverage and API availability |
| Windows Update diagnostics | `windows_update.py` | Implemented as bounded read-only diagnostics; manual Windows validation required | Timeout, permission failure and no unintended install/restart |

## System, phone and release infrastructure

| Area | Current evidence | Audit state | Release gate |
|---|---|---|---|
| CPU/RAM/GPU metrics | psutil/NVML paths and HUD | Implemented / hardware dependent | Compare displayed readings with Windows tools |
| CPU temperature | HUD and voice system-status now use the shared resolver; LHM HTTP, legacy LHM WMI, Windows ACPI fallback and psutil; provider metadata exposed | Source mismatch repaired in code and covered by tests; live hardware and permission behavior remain unverified | Same provider/value in header, Settings and spoken system status; distinguish ACPI thermal zone from CPU package; confirm no admin elevation is required for supported source |
| Location and weather | Windows Geolocation API, OpenStreetMap/Open-Meteo path, WinRT Foundation dependency and PyInstaller collection added; CI import smoke test | Packaging fix added and CI-tested; Windows permission, location fix and weather remain unverified on the user's PC | Fresh packaged import, allow/deny permission, coordinates, timeout, privacy opt-out and weather response |
| Phone Remote | QR pairing, local dashboard, controls and package-asset tests | Partial / manual end-to-end required | Pair, reconnect, authentication, screen view, file transfer and interruption |
| Updater | GitHub release check, SHA-256, safe extraction, PowerShell replacement/rollback tests; one `CHECK & INSTALL UPDATE` button chains check → download → verify → confirmation → install | Combined UI flow and tests added; a real higher-version release/update cycle and successful restart/rollback remain unverified | Old-version → new-version install, no-update path, corrupt checksum, cancel, preservation of config/memory, rollback and restart |
| Windows installer | Existing build produces a one-folder PyInstaller package and release ZIP | Not yet built as a public installer | Installer only after feature audit and Windows smoke tests |
| Security and privacy | Gitleaks CI, secret/config handling, remote authentication and permission checks | Partial / manual security review required | No secret in package, no unintended public exposure, access indicators work |

## Roadmap items not established as complete in this source

The repository does not currently establish complete end-to-end implementations for cross-device cloud profile sync, full offline voice/AI parity, biometric/Windows Hello authentication, gesture control, facial-recognition multi-user profiles, autonomous social posting, health/fitness platform integration, personal expense tracking, or a complete public third-party integration API. These must not be presented as shipped features.

## Installer release gates

1. Complete the action false-success lifecycle audit across every tool family; verify postconditions where possible and add timeout/permission/cancellation regression cases. The new close-window action and app-launch verification are only the first coverage layer.
2. Complete the Windows feature matrix: voice/audio, app control, browser, files, media, memory, phone remote, system metrics, location/weather and updater.
3. Confirm CPU-temperature parity on target hardware and validate packaged WinRT location on the user's Windows installation. CI import checks alone are not live location validation.
4. Complete visual resize/DPI testing of the redesigned Settings categories and About text panel at supported window sizes.
5. Validate the single sequential updater action with a real higher-version release: check → download → SHA-256 verify → confirm install/restart. The current v3.5.2 test build reported up to date because the latest public release was also v3.5.2.
6. Run a clean Windows package smoke test and user-side acceptance tests. Record every pass/fail; do not treat source-only tests as live verification.
7. Only then create the user-facing Windows installer. Future in-app updates should be delivered by ORI's updater, not by asking users to download ZIP files.


## Additional updater safety note

The public test build used in the 13 November 2026 user-side check carried version 3.5.2, matching the latest published GitHub release tag v3.5.2. Therefore the updater correctly displayed **ORI is up to date**; this did not exercise download or install. A real end-to-end update test needs a higher versioned release asset.

The self-update helper excludes `api_keys.json` from the staged file copy, preserving the user's configured API key during the in-place update. It creates a rollback copy before replacing program files and verifies the installed executable hash. The updater tests assert that secret-preservation exclusion remains in the helper.
