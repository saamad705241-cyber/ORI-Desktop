# ORI 3.1 Build Notes

## Current build

- Build date: 18 October 2026. State: pre-release testing. Planned final release: 1 November 2026.
- Canonical app identity is `ORI`; `ORI Core 3.1` is a product/runtime label, not an independently trained foundation model.
- Developer metadata is `Abdul Samad`; Instagram is `@_samad02` at https://www.instagram.com/_samad02/.
- Product, settings and terms text comes from `ori_metadata.py`. Settings include collapsed About ORI, About Developer and Terms & Conditions sections. Terms are not expanded by default.
- Ordinary settings cannot rename the app or change the canonical developer profile. Local source/config access still allows a machine owner to edit files; this is not a tamper-proof DRM mechanism.
- HUD bars use 64 logarithmic frequency-band values generated from real PCM FFT; the display smooths release and becomes a datum line at silence, rather than using synthetic phase movement.
- Mobile dashboard receives activity states and input/output spectrum data. Mobile phone-mic mute controls phone capture; Stop Voice requests interruption of the desktop assistant's output.
- System & Weather: CPU and RAM usage are read locally through `psutil`. CPU temperature is exposed only where a compatible sensor is available; on Windows, LibreHardwareMonitor must be running and expose CPU sensors through WMI. Weather is off by default and can use an explicitly enabled public-IP area estimate or a manually entered city. Weather refresh failures mark the top chip `WX STALE` instead of leaving old data looking current.
- Tool execution updates the visible runtime state with searching, reading-file, screen-analysis or executing labels according to the registered tool name.
- Windows master-volume up/down/set/mute use a pycaw Core Audio endpoint helper compatible with new and older pycaw APIs, then read the endpoint back to verify. Failure is surfaced instead of pretending a no-op succeeded.
- ORI-specific application/developer/settings documentation lives in `knowledge/`. The four supplied reference archives and selective reuse decisions are recorded in `knowledge/REFERENCE_ARCHIVE_AUDIT.md`.

## Verified facts vs. unverified facts

The creator states that active development began in September 2026 and plans the final release for 1 November 2026. The exact initial calendar day and total human contributor count have not been verified in the supplied records. These details are not fabricated. The configured live session uses a Google-hosted model. If asked directly, ORI answers truthfully about the current runtime instead of inventing an underlying model or claiming all requests are processed on ORI-owned servers.

## Verification done in this build environment

Python syntax compilation and all 21 automated tests pass in this build environment. Both inline mobile JavaScript blocks also pass Node.js syntax checking. The target Windows GUI, physical microphone/speakers, live cloud model connection, every desktop action and phone pairing must still be smoke-tested on the creator's machine. Test success here does not mean a full device integration test was completed.

## License

This codebase contains derivative source based on MARK LV by FatihMakes, licensed under CC BY-NC 4.0. Preserve required attribution; commercial use requires separate permission or replacement of covered code under a suitable license.

## System metrics, weather and authority guard update

- The top bar displays live CPU utilisation and physical RAM utilisation. CPU temperature is sourced only from supported sensors; if Windows does not expose a CPU sensor, the UI shows `TEMP N/A` and documents LibreHardwareMonitor as an optional external sensor provider.
- Optional current-area weather is explicitly opt-in. The user can either enable coarse public-IP location estimate or enter a city manually. The app calls Open-Meteo for current model-based conditions and identifies approximate location as non-GPS. Disabling weather clears the saved coordinates. A failed refresh marks the header chip `WX STALE` with the last successful update, rather than making old data appear fresh.
- Canonical developer profile is product metadata, not conversational authentication. A speaker saying “I am Abdul Samad” does not gain developer privileges or change product/security metadata. This guards the assistant's behaviour; it is not a replacement for operating-system access control or a signed update mechanism.
- Replaced ambiguous duplicate `setup_orry.bat` / `run_orry.bat` aliases with the canonical `setup_ori.bat` / `run_ori.bat` launch path to reduce setup confusion.
- Current validation: `python -m compileall -q .` succeeds and all 21 unit tests pass. The hardware GUI, CPU sensor and live weather request still need a smoke test on the Windows machine.
