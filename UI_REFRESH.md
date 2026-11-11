# ORI 3.1 UI refresh

The home surface is intentionally minimal: ORI status, one central audio waveform, a command field, compact microphone mute and Stop Voice controls, and a single Settings entry. No face, head, avatar, animated orb, metrics card, or persistent activity side panel is displayed.

The waveform is driven by actual microphone PCM and speaker-output PCM. With no measurable audio, the centre is a stable straight line rather than a decorative idle animation. Desktop and paired-phone views use the same dark terminal / phosphor-green visual language.

Settings are presented in one scrollable page. It contains the Google-hosted AI connection, voice and audio devices, interface/access options, integrations, About ORI, the developer/Instagram link, and full Terms & Conditions. Save/apply buttons switch to a saved state and revert when a related control is edited again.

The phone dashboard supports secure pairing, text commands, file transfer, local phone-microphone voice input, phone-mic mute, remote speech interruption, and the matching waveform HUD. A remote interrupt request is authenticated by the paired session and calls the desktop assistant's interruption callback.
