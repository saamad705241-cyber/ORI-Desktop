# ORI 3.3 Build Notes

This build is based on the user-supplied original ORI 3.1 project. Its PyQt6 desktop runtime, Gemini Live path, 64-band PCM spectrum, original chat input, desktop actions, memory and phone dashboard are retained. Changes focus on Settings usability, first-run clarity, temperature provider probing, and phone dashboard reliability.

The phone dashboard binds to a free LAN port beginning at 8000 rather than assuming 8000 is available. It sends the selected URL and startup error back to the UI. The paired phone can explicitly request a screenshot through an authenticated endpoint.

Settings are category-based and no longer use a page-level QScrollArea. Google/email login are marked Coming Soon rather than mocked.

License/attribution notices from the original archive remain included. The original archive's CC BY-NC 4.0 restrictions continue to apply to derivative components.
