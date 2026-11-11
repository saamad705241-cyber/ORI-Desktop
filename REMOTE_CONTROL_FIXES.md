# ORI 3.1 Remote Control Fixes

## What was corrected

- The phone pairing URL could be generated before the first-run HTTPS certificate was created. In that timing window ORI could display an `http://` QR link even though the dashboard later started on `https://`. The server now selects its transport before the UI can request a pairing link, and the same choice is used by both the URL generator and Uvicorn.
- The machine's LAN IP can change when switching Wi-Fi networks. ORI now validates the saved certificate against the current LAN IP, certificate dates, and private-key match, then regenerates it when stale. The manual-entry URL includes `https://` or `http://` explicitly instead of relying on browser auto-upgrade behavior.
- LAN IP discovery now enumerates active network interfaces as a fallback, which is more reliable on systems where hostname lookup resolves only to loopback.
- The Phone Remote Control settings now show when the dashboard has actually started. Startup/dependency/port errors are surfaced rather than leaving the panel stuck on “starting”.
- Remote status and phone-connected UI updates now use Qt signals, so the runtime thread does not directly modify Qt widgets.
- ORI now refuses to create a pairing key before the dashboard is ready and writes a useful message to the activity log.
- Added regression tests for HTTPS/HTTP link consistency, pairing-key creation, and QR auto-login.

## Verification performed

- `python -m compileall -q .` completed successfully.
- `python -m unittest discover -s tests -q`: 81 tests passed.
- Embedded JavaScript from `dashboard/static/app.html` passed `node --check`.

## Remaining on-device test

A real phone-to-PC connection and Windows firewall behavior cannot be proven in this build environment. To test, start ORI on Windows, wait until Settings → Phone Remote Control says “Dashboard running”, then use Remote Control or Show QR Code while the phone and PC are on the same Wi-Fi. If ORI uses its local self-signed HTTPS certificate, the phone browser may show a certificate warning. Only continue after confirming the address is your PC's local IP and you are on your trusted local network. Do not expose the dashboard to the public internet.
