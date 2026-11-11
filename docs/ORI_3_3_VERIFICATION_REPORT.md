# ORI 3.3 — Verification Report

## Automated checks completed in this build environment

- Python unit tests: **96 passed**.
- Python source compilation: passed (`python -m compileall -q .`).
- Mobile dashboard inline JavaScript syntax: passed with Node.js.
- JSON files: parsed successfully.
- TOML files: parsed successfully.
- Dynamic dashboard port selection and authentication boundary for PC screenshot capture: covered by tests.
- Settings redesign contracts (category stack, no `QScrollArea`, no numbered headings, no Firebase/browser/model list) and onboarding state: covered by tests.
- ZIP integrity: checked before delivery.
- Secret scan by file inventory: no `config/api_keys.json`, `.env`, TLS private key, or certificate is bundled.

## Checks unavailable in this environment

- PyQt6 is not installed in the build environment, so I could not render the Settings pages or capture a new live GUI screenshot here.
- Ruff is not installed, and package registry DNS is unavailable in this environment, so the Ruff command could not be run.
- Windows-specific GUI execution, microphone/speaker selection, WMI hardware temperature reading, live Gemini connection, QR scan from a physical phone, and phone-to-PC screenshot capture require testing on the target Windows computer.

## Expected first-run behavior

1. Continue with Google is shown; clicking it reports Coming Soon.
2. Email address and Send Email Code are shown; clicking it reports Coming Soon. No email is sent in this build.
3. Continue as a Guest works.
4. Guest preferences ask for name, language and conversation style; Skip uses safe defaults.
5. A Google AI Studio API key is verified before being saved for Gemini use.

## Remote pairing notes

- The dashboard selects an available port beginning at 8000 and reports actual startup errors.
- Phone pairing requires the PC and phone to share a trusted LAN/Wi-Fi network.
- Windows Public network profiles are not silently converted to Private and firewall rules are not opened on Public networks.
- PC screenshot capture is a paired-device-only endpoint and runs only after an explicit phone action.

## CPU temperature notes

ORI tries LibreHardwareMonitor and OpenHardwareMonitor WMI namespaces. If neither provider exposes a CPU sensor, the UI must show N/A and explain that a sensor provider is required. It must not fabricate a temperature value.
