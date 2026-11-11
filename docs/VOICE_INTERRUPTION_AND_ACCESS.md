# Voice interruption and access indicators

## Interrupting long actions

Long text-entry operations use cooperative cancellation. They type/paste small batches and check a cancellation event between batches. The keyboard interrupt, stop control, or verified voice barge-in requests cancellation. An operation reports the number of characters entered before it stopped.

Voice barge-in uses two gates while ORI is speaking: WebRTC VAD (speech activity) and the adaptive EchoGuard (rejecting ORI's own speaker echo). During a long action with no ORI playback, sustained VAD speech can interrupt the action. Short noise/clicks should not meet the sustained speech threshold.

This is speech-vs-noise/echo detection, not biometric speaker identification. ORI does not claim to verify a particular person's identity from their voice.

## Access indicators

The top bar shows blinking indicators only while a controlled capability is active: MIC, SPK, SCREEN, KEYS, MOUSE, WEB, FILES, CAM, NET and SYSTEM. These reflect app-controlled activity; Windows itself may continue background system activity outside ORI's control.

## Continuous screen monitoring

The user must explicitly ask ORI to start watching the screen. ORI then sends up to one JPEG/PNG frame per second to the active Gemini Live session. The SCREEN indicator stays visible. Saying "stop watching my screen" calls the stop tool, cancels the capture task and clears the indicator. Frames are not saved to disk by the watcher. This feature requires a compatible Gemini Live session and valid network connectivity; usage may consume API quota.
