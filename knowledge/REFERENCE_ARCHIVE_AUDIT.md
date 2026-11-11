# Reference archive audit — ORI 3.1

This document records the purpose of each archive supplied by the project creator, how it matches ORI's requirements, and which parts were selected, adapted conceptually, or deliberately not copied. It is an engineering audit, not a claim that all external feature sets are already implemented.

## 1. `Jarvis-Download-Files.zip`

**Contents observed:** a VoiceBot macro profile, a setup guide in DOCX, an activation-prompt PDF, a disclaimer presentation, and an image/diagram. The macro profile is an automation for controlling the ChatGPT Desktop voice UI, not a complete standalone assistant backend.

**Useful ideas:** documented activation steps, explicit setup instructions, disclosure of macro fragility, and a clear assistant voice-style profile.

**Not copied:** the macro flow's dependency on another application's UI is not used as ORI's core runtime. The exact Marvel/fictional JARVIS character imitation is not copied; ORI keeps an original, calm terminal-operator style. The disclaimer warns about dependencies and limitations, which informed ORI's terms and setup guidance.

## 2. `Jarvis-master(1).zip`

**Contents observed:** a MIT-licensed Python, voice-activated natural-language UI with separated listener/speech code, a spectrum-listener module, offline helpers, file I/O, secure-send and stats/API routes/tests. Its README targets a different dependency and runtime layout.

**Useful ideas selected:** separating PCM spectrum computation from GUI drawing, testable audio helpers, clear optional-feature dependencies, and explicit success/error handling. ORI now uses an independently written log-spaced FFT helper (`core/audio_spectrum.py`) and tests it against silence and distinct tone frequencies.

**Not copied wholesale:** its interface, package imports, environment assumptions and server routes aren't drop-in replacements for ORI's Qt/Gemini Live runtime. No JavaScript/React/Tauri migration was done merely for aesthetics. Its MIT license would permit reuse with conditions, but reused code must retain the corresponding MIT notice.

## 3. `Mark-LV-main(1).zip`

**Contents observed:** the upstream source base for the current ORI desktop app. It includes Gemini Live voice, audio-device helpers, echo/undo/confirm modules, a plugin/action registry, browser/file/desktop/system/YouTube actions, persistent memory, wake-word support and a mobile dashboard with pairing/remote commands.

**Used in ORI:** this is the principal derivative base for the existing app. Its actions, voice/session model, UI and remote dashboard were retained and revised rather than replacing working subsystems with unrelated stacks. ORI's product knowledge and identity metadata are maintained in one explicit metadata module. Actual action completion must still be verified at runtime.

**Critical license note:** the supplied source includes a CC BY-NC 4.0 license. The non-commercial condition prevents treating this build as already cleared for paid/commercial distribution. Required attribution stays in the bundle; obtain separate permission or replace covered code before commercial use.

## 4. `N.E.K.O-main.zip`

**Contents observed:** a large local-first AI companion runtime with conversation and multimodal pipelines, persisted memory and recall, schema-driven providers, agent/tool services, plugins, memory UIs, test infrastructure and avatar surfaces. The repository describes its core as Apache-2.0 licensed, but bundled models, assets, plugins and dependencies may carry separate license terms.

**Useful ideas:** memory boundaries, provider abstraction, capability registration, explicit task/activity state, plugin lifecycle and testing gates. These are architecture patterns, not automatic feature transfers.

**Deliberately not merged wholesale:** it is a substantial companion/avatar product with several frontend/runtime surfaces and many dependencies. Bringing it in wholesale would add significant size, conflicting UI concepts and separate license obligations. ORI's deliberate product constraint is a waveform-only HUD without a face/avatar, so N.E.K.O.'s avatar/embodiment system was not imported. No N.E.K.O source/assets are intentionally copied in this build.

## Cross-reference decisions

| ORI requirement | Decision | Current implementation status |
|---|---|---|
| Product/developer knowledge | Central `ori_metadata.py`; injected into live system prompt; also documented in `knowledge/` | Implemented in source; response quality needs live-session validation |
| Correct creator/handle and release roadmap | Single metadata source; `@_samad02`; September 2026 start month; planned 1 Nov 2026 release | Implemented; exact start day/team count deliberately not invented |
| Collapsible Settings/About/Terms | Desktop collapsible Settings sections; mobile details require explicit click | Implemented in source; target-screen visual QA remains |
| Real frequency behavior | 64 log-spaced bands from FFT on live PCM; no synthetic phase oscillation; slow decay | Implemented in source and unit tests; requires testing against real speakers/mic |
| Real desktop volume change | Prefer Windows Core Audio endpoint API; re-read and verify requested value; fail instead of false success | Implemented in source; Windows hardware smoke test remains |
| Phone remote activity state | Desktop status is broadcast to authenticated dashboard; remote displays normalized activity state | Implemented in source; multi-device/network test remains |
| All referenced features | Reuse only where architecture, license and product goal fit | Not every upstream feature is merged; each action must be implemented and tested individually |

## Public project references consulted

- AnaaySampat, `jarvis-windows`: https://github.com/AnaaySampat/jarvis-windows — HUD, browser/desktop automation, mobile pairing and action verification patterns. Verify current license and bundled package/model licenses at the source before copying any code/assets.
- deepakrakshit, `jarvis-ai`: https://github.com/deepakrakshit/jarvis-ai — realtime voice, echo-cancellation, Windows UI automation, mobile remote and capability-firewall ideas. The public repository lists MIT licensing; its dependency/model subcomponents still need separate review.
- Project N.E.K.O.: https://github.com/Project-N-E-K-O/N.E.K.O — memory, provider schema, tools/plugins and architecture concepts; no whole-project merge.
- pycaw: https://github.com/AndreMiras/pycaw — Windows Core Audio endpoint control and read-back verification for master volume.

No external repository is treated as proof that its features are working in ORI. The actual runtime registry, device behavior, permissions, dependency availability and tests determine ORI's advertised capabilities.
