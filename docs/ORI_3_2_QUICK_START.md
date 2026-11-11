# ORI 3.2 — Quick Start

1. Extract this archive into a new folder such as `C:\Users\<you>\Downloads\ORI_3_2`.
2. Open that folder in File Explorer.
3. Click the address bar, type `cmd`, and press Enter.
4. Run `setup.bat` and wait for `ORI 3.2 setup complete`.
5. Run `run.bat`.
6. On first launch, select **Continue as a Guest**. Account sign-in is not yet enabled.
7. Enter a preferred name, language and conversation style.
8. Paste a Google AI Studio API key. ORI verifies it before saving.
9. Allow Windows microphone access. ORI starts its Gemini Live session and opens the microphone unless you have enabled mute or push-to-talk/wake-word behavior.

## Everyday use
- Speak naturally to ORI; the text/chat input at the bottom remains available.
- `MUTE MIC` mutes the PC microphone. `UNMUTE MIC` opens it again.
- `STOP VOICE` interrupts ORI's current speech without muting the microphone.
- Press F4 to mute/unmute and Esc to interrupt, as shown in the HUD footer.
- Open Settings with the top-right Settings control or `Ctrl+,`.

## System display
Settings → System Display:
- Percentages only
- Graphs only
- Percentages + graphs

Temperature is measured in degrees Celsius and appears only when a compatible sensor is exposed. If no sensor is found, ORI displays N/A rather than guessing.

## Phone remote
Settings → Phone Remote → Show QR Code. Keep the phone and PC on the same trusted Wi-Fi network. Pair only devices you trust. The remote dashboard can send commands, stream phone microphone audio, interrupt ORI, mute/unmute the PC microphone and upload supported files to the PC.

ORI does not silently change a Windows Public network profile to Private. On a trusted Private network, Windows may ask once for permission to add a LAN-only firewall rule.

## Coming soon
Account sign-in/cloud profile sync and signed GitHub automatic updates remain marked Coming Soon. They are not presented as working until the corresponding credentials, release repository and end-to-end tests are complete.
