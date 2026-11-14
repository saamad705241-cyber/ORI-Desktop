# ORI Windows installer and update contract

## Distribution

- Build the application with PyInstaller in one-folder mode. The bundle includes the Python runtime and collected Python packages; users do not install Python, Java or Node.js.
- Wrap the complete `dist/ORI` payload in the Inno Setup `ORI-Setup-x.y.z.exe` installer.
- Install per-user at `%LOCALAPPDATA%\Programs\ORI`. Setup must not request administrator rights.
- The installer creates a Start Menu shortcut, offers an optional desktop shortcut, and registers a normal Windows uninstall entry.

## Persistent user data

Program files live in the install directory. Credentials, preferences and memory live separately under `%LOCALAPPDATA%\ORI`:

- `config/api_keys.json`
- `memory/long_term.json`
- `downloads`, `screenshots`, `logs`, and updater state

The application migrates existing portable config and memory once, without overwriting newer user data. Uninstall removes the installed program and shortcuts, but deliberately keeps this data. The Settings uninstall note explains this.

## In-app update flow

1. The single **Check for Updates** button queries the latest GitHub release only. It never downloads.
2. If a newer release exists, that same button changes to **Download Update**. Clicking it downloads the matching `ORI-Setup-x.y.z.exe` and SHA-256 sidecar, then verifies the checksum.
3. After verification, the same button changes to **Install & Restart**. After confirmation, a detached PowerShell helper waits for ORI to exit, backs up the program files and previous Windows version registration, runs the verified installer silently in the same install directory, launches the new ORI, and verifies its exact version, executable path and continued process liveness. Failure restores the previous program files and Windows version registration.

The helper, transcript and rollback data are kept under `%LOCALAPPDATA%\ORI\updates`, outside the directory being replaced.

## One-time bootstrap for older installed versions

ORI 3.6.0 and 3.6.1 contain the older updater helper. Install the official ORI 3.6.2 or later Setup manually once to enable in-app updates. Portable ZIP builds also require one manual Setup installation. After bootstrap, later releases can be installed from the single progressive in-app update button.

## Validation required for a public release

- Build and compile the installer on Windows CI.
- Run automated tests for release asset discovery, checksum verification, user-data migration, media synchronization and update helper contracts.
- Install on a clean Windows 10/11 user account with no Python, Java or Node.js installed.
- Verify first launch, API-key onboarding, audio, media, Phone Remote and user-data persistence.
- Update from an installed previous version using the three explicit UI stages.
- Exercise bad checksum, interrupted download, failed setup, failed startup and rollback.
- Verify the uninstall entry, Settings uninstall flow, and user-data retention.

A successful CI package build is not a substitute for the clean-machine install/update test.
