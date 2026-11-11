# ORI 3.1 — Feature Implementation Matrix

Last updated: 18 October 2026 (pre-release testing)

Status key:
- ✅ Implemented and verified (automated tests pass)
- 🔶 Implemented — awaiting real-environment verification on Windows
- 🔷 Partially implemented
- ⛔ Blocked by dependency / hardware / external credential
- ❌ Not yet implemented

---

## PART A — Core AI and Architecture

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 1 | Real-time data processing | ✅ | Gemini Live streaming pipeline in main.py |
| 2 | Desktop control and file management | 🔶 | actions/* registered; Windows smoke-test required |
| 3 | Natural voice interaction | 🔶 | STT/TTS via Gemini Live; device test required |
| 4 | Privacy controls | ✅ | Prompt guard, secret redaction, opt-in location |
| 5 | Adaptive personalization | 🔷 | Memory system in place; learning loop partial |
| 6 | Cross-device synchronization | ❌ | Planned; out of scope for 3.1 |
| 7 | Proactive context awareness | 🔷 | Proactive checks in prompt; limited triggers |
| 8 | Self-updating architecture | 🔷 | Plugin loader present; update check not automated |
| 9 | Local AI (privacy-first) | 🔷 | local_runtime.py scaffolded; Gemini is mandatory AI backend per spec |
| 10 | Initial onboarding | 🔶 | API key setup flow exists; full wizard pending |
| 11 | Secure environment configuration | ✅ | config_manager.py; credential in api_keys.json |
| 12 | Personalized voice/communication | 🔶 | Voice selection in Settings; Hinglish/Hindi in prompt |
| 13 | Transparent data usage | ✅ | Terms text in ori_metadata.py; shown in Settings |
| 14 | Robust error handling | 🔷 | Reconnect backoff in main.py; partial coverage |
| 15 | Cross-platform readiness | 🔷 | OS guards in actions; macOS/Linux not smoke-tested |

## PART B — Media and Entertainment

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 17 | Advanced media playback | 🔶 | video_player.py + crash fix applied in this build |
| 18 | Audio-only streaming | 🔷 | QMediaPlayer audio path present; explicit mode missing |
| 19 | Gesture/voice media navigation | 🔷 | Voice commands routed; gesture hardware not tested |
| 20 | Multiple media formats/sources | 🔶 | Local file + YouTube (yt-dlp) + direct URL |
| 22 | Internal media player (local audio) | 🔶 | Qt multimedia backend; Windows codec pack may be needed |

## PART C — Search, Productivity, Development

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 25 | Built-in local media file search | 🔷 | file_controller.py has music/video path discovery |
| 26 | Ad-free experience for local media | ✅ | Local playback has no ads by definition |
| 27 | Local caching with expiration | 🔷 | Gemini response cache in gemini.py; TTL partial |
| 28 | Advanced file processing/analysis | 🔶 | file_processor.py; depends on runtime permissions |
| 29 | Self-diagnostics and error reporting | 🔷 | Logs to stdout; structured error model partial |
| 30 | Customization and accessibility | 🔷 | Accent color in UI; accessibility not audited |
| 31 | Scheduling and task automation | 🔷 | reminder.py present; recurring tasks not complete |
| 32 | System config and update validation | 🔷 | computer_settings.py; Windows Update module pending |
| 33 | Developer identity handled accurately | ✅ | ori_metadata.py + prompt.txt updated in this build |
| 34 | User documentation and help | 🔷 | README.md + knowledge/ docs; in-app help partial |

## PART D — Hardware, Privacy, Advanced Automation

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 35 | First-run hardware/permission detection | 🔷 | installer.py scaffolded; full onboarding wizard pending |
| 36 | Optional weather/location setup | 🔶 | Settings flow exists; opt-in enforced |
| 37 | Hide unavailable sensor info | ✅ | TEMP N/A when sensor absent; N/A for unavailable readings |
| 38 | System performance diagnostics | 🔶 | psutil CPU/RAM in system_monitor.py |
| 39 | Granular notifications | 🔷 | UI log notifications exist; granular controls partial |
| 40 | Backup and restore | ❌ | Config backup not yet automated |
| 41 | Diagnostic history and logging | 🔷 | stdout logs; rotation/redaction partial |
| 42 | Workflow automation and macros | 🔷 | Actions registered; macro recording not implemented |
| 43 | NLP for ambiguous commands | ✅ | Handled by Gemini reasoning layer |
| 44 | Biometric authentication | ❌ | Windows Hello integration not yet implemented |
| 45 | Multi-user profiles | ❌ | Single-user only in 3.1 |
| 46 | Interactive tutorials/in-app help | ❌ | Planned post-release |

---

## Backend Stability Modules (this build)

| Module | Status | Notes |
|--------|--------|-------|
| core/context_refresh.py | ✅ | 3-hour scheduled refresh; configurable interval |
| core/cleanup_service.py | ✅ | Periodic RAM cleanup; registered cleaner pattern |
| Video crash hardening (ui.py) | ✅ | _reset_video_players() + error hook |
| Developer identity fix (prompt + metadata) | ✅ | Normal intro → normal conversation |
| ORI acronym + tagline (ori_metadata.py) | ✅ | Full form, meanings, tagline in About/knowledge |

---

## What still requires the Windows machine

- Microphone and speaker device test
- Gemini Live end-to-end voice round-trip
- Windows desktop automation (pyautogui, pycaw, win32api)
- QR phone pairing on local network
- CPU temperature sensor via LibreHardwareMonitor
- Video playback multi-track stability after crash fix
- Browser automation via Playwright on a real Chrome install
