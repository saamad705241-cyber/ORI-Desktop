# ORI 3.4 Phone Remote

## Included remote controls

- Original one-time QR pairing and authenticated browser dashboard.
- Relative touchpad: one-finger move, tap/left click, two-finger scroll and
  right-click gesture, adjustable pointer and scroll sensitivity.
- Keyboard shortcuts: Esc, Tab, Enter, Alt+Tab and Show Desktop; type text into the currently-focused PC app (including Unicode via clipboard).
- Quick actions: media previous/play-pause/next, volume up/down/mute, Show
  Desktop, File Explorer, Switch App, Lock PC, PC microphone mute and Stop ORI.
- Live PC screen preview over authenticated WebSocket JPEG frames (target 6 FPS,
  capped at 8 FPS; the stream stops when the Screen view is left).
- Single PC screenshot capture and existing file upload/download, phone voice,
  wake and interrupt controls.
- Optional phone screen frame ingestion. A screen frame is sent to Gemini only
  when the user presses **ASK ORI ABOUT THIS SCREEN**.
- Android MediaProjection source project in `android-companion/` for devices
  whose mobile browser cannot capture the full phone screen.

## Network behavior

The PC and phone must be on the same trusted private Wi-Fi/LAN. ORI binds the
remote dashboard to a dynamically selected available port starting at 8000 and
reports its actual address only after Uvicorn has bound successfully. It does
not change a Windows network profile or open a public internet port.

If the settings page still says that the dashboard is starting, read the exact
error shown there and the console line beginning `[Dashboard]`. Common causes
are no usable LAN IPv4 address, FastAPI/Uvicorn not installed, or Windows
Firewall blocking the local network. The `/health` endpoint reports dashboard
readiness and the active port.

## Browser and screen-sharing limitation

The web remote's phone screen-share button feature-detects
`navigator.mediaDevices.getDisplayMedia()`. That API requires a secure context
and is not available in Chrome for Android. For Android full-device sharing,
use the native companion source project. Browser support varies by OS/browser;
the UI reports unsupported capability instead of pretending to share.

## Privacy

- Desktop screen frames are generated only while a paired phone has the live
  PC Screen view open.
- Phone screen frames are accepted only from an authenticated paired device.
- The latest phone frame is kept in memory and expires from analysis eligibility
  after 30 seconds. It is not saved to disk.
- Gemini receives the frame only after an explicit user request to analyze it.
- Pairing is designed for a trusted private LAN, not the public internet.


The Android companion token is held by the local ORI server in memory. If ORI
restarts, create a new one-time pairing code and pair the companion again.
