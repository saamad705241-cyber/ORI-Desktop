# ORI roadmap

This document records requested follow-up features. Items listed here are planned, not claims about the current build.

## Media playback controls

- Keep playback in ORI's own HUD; do not open Chrome simply to play a supported media source.
- Provide reliable play, pause, resume, stop, next, previous, seek/skip, volume and mute controls.
- Support a queue/playlist and automatic next-track behavior.
- Voice commands and on-screen controls must use the same playback state so they cannot fight each other.
- Report whether the player is playing, paused, buffering, ended or failed; do not claim success from a request alone.

## Live network speedometer

- Add an analog, motorcycle-style needle gauge that fits ORI's minimal terminal HUD.
- Show live download and upload rates in KB/s or MB/s, plus session data totals.
- Distinguish total PC network traffic from ORI-specific traffic where the platform can measure it reliably.
- Keep the gauge lightweight and sample network counters off the UI thread.
- Display an unavailable state rather than inventing a speed when counters cannot be read.

## Delivery order

1. Stabilize the current voice/audio output and internal video playback.
2. Complete the per-user Windows Setup installer, uninstall flow and Check → Download → Install updater.
3. Verify the installer on a clean Windows 10/11 account, including a full update and rollback.
4. Add media transport controls.
5. Add the analog network speedometer.
6. Resume account/Firebase work only after the installer/update milestone is verified.
