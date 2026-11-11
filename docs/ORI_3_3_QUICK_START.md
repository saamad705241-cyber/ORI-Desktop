# ORI 3.3 — Quick Start

1. Extract the ZIP to a new folder; do not overwrite an older ORI directory.
2. Run `setup.bat`.
3. Run `run.bat`.
4. On first launch, Google sign-in and email OTP are visibly marked Coming Soon. Choose `Continue as a Guest`.
5. Enter your name and optional preferences, or choose Skip.
6. Paste one Google AI Studio API key and verify it. ORI selects its compatible Gemini model automatically.
7. Open Settings → Phone Remote → Pair Phone. Keep PC and phone on the same trusted Wi-Fi.

## Remote screenshot
A paired phone can request a PC screenshot using the PC SCREEN button. The endpoint requires an authenticated pairing token.

## CPU temperature
Temperature is displayed only when a supported hardware sensor is exposed. On Windows, run LibreHardwareMonitor or Open Hardware Monitor with its WMI sensor provider enabled, then choose Settings → System → Recheck CPU Sensor. ORI never invents a temperature.

## Account sign-in
Google sign-in and numeric email OTP are not implemented in this build. Their UI says Coming Soon. Guest mode works locally.
