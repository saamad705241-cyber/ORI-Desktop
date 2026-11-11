from __future__ import annotations

from importlib import metadata
from pathlib import Path


def license_label(dist) -> str:
    meta = dist.metadata
    value = str(meta.get("License") or "").strip()
    if value and value.lower() not in {"unknown", "license :: other/proprietary license"}:
        return value.replace("\n", " ")
    classifiers = [
        item.split("::", 2)[-1].strip()
        for item in (meta.get_all("Classifier") or [])
        if item.startswith("License :: OSI Approved ::") or item.startswith("License :: OSI Not Approved ::")
    ]
    if classifiers:
        return "; ".join(classifiers)
    return "REVIEW REQUIRED — distribution metadata does not declare a license"


def main() -> int:
    rows = []
    for dist in sorted(metadata.distributions(), key=lambda item: (item.metadata.get("Name") or "").lower()):
        name = dist.metadata.get("Name") or "unknown"
        version = dist.version or "unknown"
        rows.append((name, version, license_label(dist)))
    output = [
        "# Generated third-party license inventory",
        "",
        "Generated from the currently installed environment. It is not a substitute for reviewing package license files and the dependency versions in the release artifact.",
        "",
        "| Distribution | Version | License metadata |",
        "|---|---:|---|",
    ]
    for name, version, license_name in rows:
        safe = lambda value: str(value).replace("|", "\\|").replace("\n", " ")
        output.append(f"| {safe(name)} | {safe(version)} | {safe(license_name)} |")
    path = Path("THIRD_PARTY_LICENSES.generated.md")
    path.write_text("\n".join(output) + "\n", encoding="utf-8")
    print(f"Wrote {path} with {len(rows)} distributions. Review all REVIEW REQUIRED rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
