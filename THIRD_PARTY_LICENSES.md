# Third-party license register

## Inherited ORI source

The supplied ORI 3.1 archive identifies portions of the inherited application as derivative of **MARK LV by FatihMakes**, licensed under **CC BY-NC 4.0**. See `ATTRIBUTION.md`, `UPSTREAM_MARK_LV_README.md`, `LICENSE` and the upstream source notices. This is a non-commercial license; commercial redistribution requires separate permission or replacement of restricted portions with independently licensed code.

## Runtime dependencies

ORI uses packages declared in `requirements.txt`. Their exact license terms are those shipped with the exact installed distribution version. Do not infer that every dependency shares ORI's license. Before distributing a built application, run:

```cmd
python scripts\export_licenses.py
```

This writes `THIRD_PARTY_LICENSES.generated.md` using the installed Python package metadata and marks any distribution whose license metadata is missing or ambiguous for manual review. Keep the original package license files with the release and review PyQt6's licensing option before publishing binaries.

Key integrations include PyQt6, Google Gen AI SDK, FastAPI/Uvicorn, Requests, Playwright, WebRTC VAD, PyAutoGUI, Pillow, OpenCV, psutil, qrcode, cryptography and pywin32. Each retains its own copyright and license.

## Assets

- `config/ori.ico`: ORI project icon asset retained from the supplied archive.
- `config/instagram.svg`: Instagram brand mark used only as a link to the configured project profile. Instagram is a trademark of Meta Platforms, Inc.; this is not an endorsement.
- `dashboard/static/`: remote dashboard assets are inherited and must be reviewed against the upstream notices before redistribution.
