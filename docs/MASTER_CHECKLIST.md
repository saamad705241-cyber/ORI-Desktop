# ORI Master Development Checklist

This is the single source of truth for ORI's remaining development work.
The current published baseline is ORI 3.5.0; the active patch candidate is ORI 3.5.1. Do not create a final installer or
declare a final release until the acceptance checks in the final phases pass.

## Current baseline

- [x] GitHub repository is published.
- [x] ORI 3.5.0 stable release is published.
- [x] GitHub CI, automated tests, Ruff checks and Gitleaks have passed.
- [x] Windows one-folder package can be built by CI.
- [x] The GitHub updater repository is configured.
- [x] The user reports the current update flow is working. Do not rewrite its backend
      without a demonstrated regression.
- [x] Phone Remote QR pairing and controls work in Python/source mode.
- [ ] Phone Remote does not become ready in the packaged Windows build.
      **DEFERRED:** keep the known issue on the backlog. Do not spend the current
      development cycle on it. Revisit after ORI has a larger user base or when
      the user explicitly requests it.
- [x] Primary development hardware has been inventoried: ASUS TUF Gaming A16
      FA607NUQ, AMD Ryzen 7 170 (8 cores / 16 threads), 16 GB Micron RAM,
      AMD Radeon Graphics, NVIDIA GeForce RTX 4050 Laptop GPU, FA607NUQ
      motherboard, KIOXIA 512 GB SSD, Windows 11 build 26300.

## ORI 3.5.1: CPU temperature, startup location and microphone/voice controls

- [ ] Parse CPU package/Tctl/Tdie readings from LibreHardwareMonitor's local HTTP JSON endpoint at 127.0.0.1:8085/data.json, with legacy WMI and psutil fallbacks.
- [ ] Use the same CPU-temperature provider in the live top-bar metric and hardware_inventory action.
- [ ] Add first-launch location consent, then request Windows device-location access on the foreground UI thread.
- [ ] Fetch current weather and locality only after explicit consent; keep coordinates in local configuration and provide disable and Windows privacy-settings controls.
- [ ] Add a visible Location & Weather section in System Settings.
- [ ] Add bundled microphone-on, microphone-muted and stop-voice icons to the home controls.
- [ ] Verify tests, Gitleaks, Ruff and the Windows PyInstaller package in CI.
- [ ] Physically verify CPU temperature with LibreHardwareMonitor Remote Web Server enabled, Windows location consent, and the microphone controls on the ASUS development laptop.

Physical verification note: LibreHardwareMonitor 0.9.5+ no longer supplies the legacy WMI sensor namespace. For LHM 0.9.6, its local Remote Web Server must be enabled (Options > Remote Web Server > Run) for ORI to read CPU temperature. ORI shows N/A when no real CPU sensor is available.

## Next-session P0: Action execution reliability (new critical bug)

**Reported 2026-11-13. This is the first task when development resumes.**

- [ ] Investigate false success confirmations: ORI says an action completed even when
      the real OS operation did not happen.
- [ ] Reproduce with "Close Notepad" and verify whether the process/window actually closes.
- [ ] Trace the complete tool path: model tool call, action handler, OS command,
      operation result, postcondition and spoken response.
- [ ] Audit generic success fallbacks (including empty handler results), swallowed
      exceptions, timeouts, rejected/blocked actions and unverified operations.
- [ ] Require structured action results with explicit success/failure, details and
      verification state.
- [ ] Verify real postconditions where practical before speaking success.
- [ ] On failure or uncertainty, report the actual outcome and next required step.
- [ ] Add regression tests for app-close and representative computer-control actions,
      covering success, failed operation, timeout, permission denied and unverified state.
- [ ] Preserve existing working actions, voice interaction and interruption behavior.

Tracking issue: https://github.com/saamad705241-cyber/ORI-Desktop/issues/5

**Priority order:** Fix and validate this P0 issue first. Then resume the in-progress
Hardware Intelligence phase. Packaged Phone Remote remains deferred as recorded below.

## Phase 1: Baseline and feature audit

- [x] Verify the official repository and published baseline.
- [x] Verify the existing CI and Windows release workflow.
- [x] Confirm the current updater repository setting.
- [ ] Finish the feature-by-feature audit of the current application.
- [ ] Record every existing feature as working, broken, incomplete or untested.
- [ ] Establish a regression-test baseline before broad integration changes.
- [ ] Protect user configuration, API keys and local memory before build/upgrade tests.

## Phase 2: Hardware intelligence

- [x] Add a read-only hardware inventory tool that ORI can invoke on demand (merged; 147 tests, Ruff, Gitleaks and Windows package validation passed).
- [ ] Report exact laptop manufacturer and model.
- [ ] Report CPU model, physical cores, logical threads and clock speeds.
- [ ] Report installed RAM, available RAM and memory-module details.
- [ ] Identify every integrated and dedicated GPU.
- [ ] Report GPU driver, VRAM, load and temperature where supported.
- [ ] Report motherboard manufacturer and model.
- [ ] Report physical drives, capacity and mounted-volume usage.
- [ ] Report Windows edition, version, build and architecture.
- [ ] Report display resolution and connected displays where available.
- [ ] Integrate real CPU temperature and supported CPU sensor readings.
- [ ] Integrate GPU temperature, hotspot and memory-junction readings where exposed.
- [ ] Add battery, fan and other sensor data only where the hardware exposes it.
- [ ] Return unavailable readings as unavailable; never invent values.
- [ ] Test on the ASUS development laptop and on a different Windows PC.
- [ ] Ensure the packaged build includes the required WMI/NVML providers.

## Phase 3: Desktop intelligence, permissions and access indicators

- [ ] Audit and complete the existing desktop overview and computer-control actions.
- [ ] Audit screen capture, visual understanding and screen question-answering.
- [ ] Verify user-controlled continuous screen monitoring and its visible activity state.
- [ ] Implement clear, contextual permission handling for microphone, audio output,
      camera, screen capture, keyboard, mouse, browser, files, local network,
      location and notifications.
- [ ] Never silently grant OS permissions or change a Public network to Private.
- [ ] Keep neutral access indicators visible while idle.
- [ ] Show active, denied and unavailable states accurately.
- [ ] Ensure a denied or unsupported capability degrades gracefully instead of
      crashing ORI.
- [ ] Verify cancellation and confirmation for sensitive/destructive computer actions.

## Phase 4: Phone Remote and Android Companion

**DEFERRED for a later update.** Do not interrupt the current development sequence
to work on this phase.

- [x] Source-mode QR pairing and remote controls were tested by the user.
- [ ] Diagnose why the packaged Windows build does not start the Phone Remote dashboard.
- [ ] Verify the remote dashboard, touchpad, keyboard and media controls in the package.
- [ ] Redesign the mobile dashboard into clear control and screen-view sections.
- [ ] Improve touchpad responsiveness and usability.
- [ ] Add a combined touchpad and screen-sharing layout.
- [ ] Add full-screen PC display viewing on the phone.
- [ ] Build and test the Android Companion APK.
- [ ] Implement native, user-consented phone screen capture and transfer to ORI.
- [ ] Test on a real Android device and the packaged Windows app.

## Phase 5: About and updater interface

- [ ] Fix About content clipping using a proper scrollable area.
- [ ] Replace the large Instagram profile button with a small clickable icon.
- [ ] Replace the three separate updater buttons with one state-driven button:
      check, download, then install and restart.
- [ ] Show update progress and actionable failure messages.
- [ ] Preserve user settings, API configuration and local memory during updates.
- [ ] Keep the existing working updater backend unless testing proves it is broken.

## Phase 6: Firebase, accounts and central analytics

- [ ] Design Firebase data structure, access rules and cost limits before enabling writes.
- [ ] Add Guest mode and account sign-in.
- [ ] Add Google sign-in; do not add OTP login.
- [ ] Keep user profiles and user-owned data isolated.
- [ ] Link an anonymous installation to an account after sign-in where appropriate.
- [ ] Track downloads separately from successful installations.
- [ ] Track total users, active users, DAU and MAU.
- [ ] Track session counts and duration.
- [ ] Track ORI versions and consented crash/diagnostic events.
- [ ] Build an admin-only statistics view.
- [ ] Add privacy notice, user consent, retention rules and security checks.
- [ ] Never send conversations, microphone audio, screen captures, private files,
      passwords or API keys to analytics.

## Phase 7: Full integration and release QA

- [ ] Integrate all completed phases without removing existing working features.
- [ ] Run the full automated test suite and static checks.
- [ ] Run real voice, interruption, memory, actions and plugin regression tests.
- [ ] Run hardware, permission, screen and system-control tests.
- [ ] Run Firebase authentication, data-isolation and privacy tests.
- [ ] Run updater download, checksum, install, restart and data-preservation tests.
- [ ] Audit every runtime dependency, dynamic import, browser asset and helper component.
- [ ] Verify third-party licenses and redistribution rights, especially inherited
      MARK LV / CC BY-NC 4.0 restrictions, before distributing binaries.
- [ ] Produce and validate a release candidate before installer work.

## Phase 8: Single Windows installer (last phase)

- [ ] Package the complete Windows application and required runtimes/dependencies.
- [ ] Include the required Python runtime, libraries, Qt resources, browser runtime,
      assets and helper components so users do not install them separately.
- [ ] Build one user-facing `ORI-Setup.exe` using the verified package.
- [ ] Add an installation wizard and Start Menu/Desktop shortcuts.
- [ ] Register ORI correctly in Windows Installed Apps.
- [ ] Provide a proper uninstaller.
- [ ] Support upgrade and reinstall without losing user configuration or memory.
- [ ] Keep personal API keys out of public builds and preserve them safely for the user.
- [ ] Back up the development environment before clean-install testing.
- [ ] Remove reliance on separately installed development tools and test using only
      the installer on the development laptop.
- [ ] Transfer the same installer to a friend's Windows laptop and test without
      separate Python/library/helper installation.
- [ ] Test install, first launch, core features, upgrade, uninstall and reinstall.

## Release rule

The final installer is the last deliverable. Do not declare ORI complete until
all required features are tested on the development laptop and the standalone
installer has been installed and tested on a second Windows PC. A successful
GitHub build alone is not proof that a feature works on a user's machine.
