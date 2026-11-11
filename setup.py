"""
ORI — one-time dependency setup.

Installs the Python dependencies for THIS operating system only: the OS-specific
packages in requirements.txt carry `sys_platform` markers, so a macOS or Linux
user never pulls Windows-only libraries (and vice-versa). Playwright's large
browser binaries are optional and are downloaded only when ORI_INSTALL_PLAYWRIGHT=1.

Two things it deliberately does NOT install:
  * the optional local wake word ("Hey Jarvis") — opt in from ORI Settings;
  * a local LLM. Gemini Live is the primary runtime; Ollama remains optional.
"""
import platform
import subprocess
import sys
from pathlib import Path

OS = platform.system()  # "Windows" | "Darwin" | "Linux"
HERE = Path(__file__).resolve().parent

MIN_PY = (3, 11)        # hard floor: below this the syntax used here won't parse
MAX_PY = (3, 13)        # highest version this is actually tested on


def _run(label: str, args: list[str]) -> None:
    print(f"\n▶ {label}")
    subprocess.run(args, check=True)


def _check_python() -> None:
    """Fail immediately and clearly rather than deep inside a pip resolver.

    A wrong interpreter is the single most common way this install goes sideways,
    and the error it produces on its own names a wheel, not the real problem.
    """
    v = sys.version_info[:2]
    if v > MAX_PY:
        # Newer is a warning, not a wall. Turning away someone who installed
        # today's Python is a worse first impression than a version that
        # turns out to work fine, and if a wheel really is missing pip says
        # so plainly.
        print(f"\n⚠️  Python {v[0]}.{v[1]} is newer than the "
              f"{MAX_PY[0]}.{MAX_PY[1]} this is tested on. Continuing — if a "
              f"package has no wheel yet, install Python "
              f"{MAX_PY[0]}.{MAX_PY[1]} and run setup with that.")
        return
    if v < MIN_PY:
        print(f"\n❌ Python {v[0]}.{v[1]} detected — ORI needs at "
              f"least Python {MIN_PY[0]}.{MIN_PY[1]}.")
        print("   Install a supported version and run setup with it, e.g.:")
        print(f"     py -{MIN_PY[0]}.{MIN_PY[1]} setup.py        (Windows)")
        print(f"     python{MIN_PY[0]}.{MIN_PY[1]} setup.py      (macOS / Linux)")
        sys.exit(1)


def main() -> None:
    print(f"⚙  ORI 3.5.0 setup — detected OS: {OS or 'unknown'}, "
          f"Python {sys.version_info[0]}.{sys.version_info[1]}")
    _check_python()

    # requirements.txt filters OS-specific extras by itself via pip markers.
    _run("Installing Python dependencies (OS-specific extras auto-filtered)…",
         [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

    # Browser binaries can be several hundred megabytes. Keep normal setup fast;
    # the owner/user can install them later if browser automation needs them.
    import os
    if os.environ.get("ORI_INSTALL_PLAYWRIGHT", "").strip() == "1":
        try:
            _run("Installing Playwright browsers (chromium + firefox)…",
                 [sys.executable, "-m", "playwright", "install", "chromium", "firefox"])
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"\n⚠️  Playwright browsers were not installed ({e}).")
            print("    Browser automation may use the installed browser fallback.")
    else:
        print("\nℹ️  Browser binaries skipped to keep first-run setup fast.")
        print("    Optional later: scripts\\install_browser_runtime.bat")

    # ── OS-specific post-install notes ────────────────────────────────────────
    if OS == "Windows":
        try:
            import win32com.client  # noqa: F401
        except ImportError:
            postinstall = Path(sys.executable).parent / "Scripts" / "pywin32_postinstall.py"
            print(
                "\n⚠️  pywin32 did not register correctly — desktop-shortcut "
                "creation will use a slower fallback. To fix it, run:\n"
                f'    "{sys.executable}" -m pip install --force-reinstall pywin32\n'
                f'    "{sys.executable}" "{postinstall}" -install'
            )
    elif OS == "Linux":
        print(
            "\nℹ️  Linux note — a few voice-controlled OS actions shell out to "
            "native tools. Install the ones you'll use via your package manager:\n"
            "    • volume      → pulseaudio-utils   (pactl)\n"
            "    • brightness  → brightnessctl\n"
            "    • reminders   → systemd (systemd-run) or 'at'\n"
            "    • open URLs   → xdg-utils          (xdg-open)"
        )
    elif OS == "Darwin":
        print(
            "\nℹ️  macOS note — volume, brightness and reminders use the built-in "
            "'osascript' / LaunchAgents, so no extra tools are required.\n"
            "    For Safari automation only: python -m playwright install webkit"
        )

    print("\n✅ ORI 3.5.0 setup complete!")
    print("   1) Launch ORI with run_ori.bat on Windows, or python main.py elsewhere.")
    print("   2) Start ORI with run_ori.bat.")
    print("   3) On first launch, paste your Google AI connection key into the setup screen.")
    print("      Create a key at https://aistudio.google.com/app/apikey")
    print("   4) The Google-hosted live AI service provides voice conversations and calls ORI registered desktop actions.")
    print("      Ollama is optional and is not the primary runtime in this build.")


if __name__ == "__main__":
    main()
