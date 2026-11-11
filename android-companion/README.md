# ORI Screen Companion for Android

This is the optional native Android companion for **phone-to-ORI screen sharing**.
The browser-based remote dashboard remains the normal phone controller. Android
Chrome currently does not expose the full-device `getDisplayMedia()` API, so a
native app is required to request Android's system `MediaProjection` permission.

## What it does

- Pairs with an already authenticated ORI phone dashboard using a one-time code.
- Requests Android's native screen-capture permission. Android shows its own
  consent prompt; the user must approve it each time the app starts sharing.
- Captures a downscaled JPEG frame about once per second and sends it to the
  paired ORI desktop over the same LAN.
- Frames are kept in ORI memory only. They are not written to disk.
- The user returns to the ORI phone dashboard and taps **ASK ORI ABOUT THIS
  SCREEN** to send the most recent frame into the active Gemini Live session.

## Build

1. Open this `android-companion` folder in Android Studio (Giraffe or newer).
2. Install Android SDK Platform 35 and a compatible JDK 17.
3. Let Android Studio sync the Gradle project.
4. Build the `app` debug APK and install it on the Android phone.

The project sources are supplied, but this environment did not have Android SDK /
Gradle tooling, so an APK has **not** been built or device-tested here.

## Pairing

1. Start ORI on the Windows PC and pair the phone normally by scanning the ORI QR.
2. In the phone's ORI Remote page, open **PHONE SHARE** and tap
   **PAIR ANDROID SCREEN COMPANION**. A one-time eight-character code appears
   and expires after five minutes.
3. Open ORI Screen Companion. Enter the ORI server address shown in the remote
   page header and the one-time code. Tap **PAIR WITH ORI**.
4. Tap **SHARE PHONE SCREEN** and approve Android's native screen-capture prompt.
5. Return to the ORI Remote web page and tap **ASK ORI ABOUT THIS SCREEN**.

## Local HTTPS certificate

ORI generates a per-install self-signed LAN certificate in
`config/certs/jarvis.crt`. Android does not trust a self-signed certificate by
itself. For HTTPS use, copy that public `.crt` file to the phone and install it
as a user CA certificate from Android Settings → Security → Encryption &
credentials → Install a certificate. The app's network security configuration
allows user-installed certificates. **Never copy `jarvis.key` to the phone.**
If ORI is configured for plain HTTP on a trusted private LAN, no certificate
installation is needed, but traffic is not encrypted.

## Security notes

- Pairing codes are one-time and expire after five minutes.
- The companion token is protected at rest with Android Keystore AES-GCM.
- ORI accepts screen frames only from a paired bearer token.
- Use trusted private Wi-Fi. Do not port-forward the ORI remote server to the
  public internet.
- Revoke paired devices from the ORI remote dashboard when finished.
