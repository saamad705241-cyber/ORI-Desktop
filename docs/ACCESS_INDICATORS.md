# ORI live access indicators

The compact top bar only displays indicators while ORI is actively using a capability:

- MIC — microphone capture is active and not muted.
- SPK — ORI is writing audio to the selected output device.
- SCREEN — a desktop snapshot is being captured or continuous screen watch is active.
- KEYS — ORI is sending keyboard input.
- MOUSE — ORI is controlling pointer/mouse input.
- WEB — ORI is interacting with a browser or web action.
- FILES — ORI is reading or changing user files.
- CAM — webcam capture/preview is active.
- NET — a Gemini Live/network session is connected.
- SYSTEM — ORI is querying or changing supported system settings.

Indicators are transient and blink while the corresponding app-managed action is active. They do not claim to enumerate Windows' own background services or every external process that may access devices.
