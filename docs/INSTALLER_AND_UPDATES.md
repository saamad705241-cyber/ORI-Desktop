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

1. **Check for Updates** only queries the latest GitHub release. It never downloads.
2. **Download Update** downloads the matching `ORI-Setup-x.y.z.exe` and SHA-256 sidecar only after the user clicks. The checksum is verified before the download is offered for installation.
3. **Install Update** asks before closing ORI, then starts a detached PowerShell helper. The helper waits for ORI to exit, backs up the current program files, runs the verified installer silently in the same install directory, launches the new ORI, and waits for a startup-ready marker plus a short stability period. A failed install/startup restores the previous program folder.

The helper, transcript and rollback data are kept under `%LOCALAPPDATA%\ORI\updates`, outside the directory being replaced.

## One-time bootstrap for older installed versions

ORI 3.6.0 and 3.6.1 contain the earlier updater helper. Install the current official Setup manually once to receive the version-aware updater in ORI 3.6.2. After that one-time step, future updates use the in-app flow. Portable ZIP builds also require one manual Setup installation.

## Validation required for a public release

- Build and compile the installer on Windows CI.
- Run automated tests for release asset discovery, checksum verification, user-data migration, media synchronization and update helper contracts.
- Install on a clean Windows 10/11 user account with no Python, Java or Node.js installed.
- Verify first launch, API-key onboarding, audio, media, Phone Remote and user-data persistence.
- Update from an installed previous version using the three explicit UI stages.
- Exercise bad checksum, interrupted download, failed setup, failed startup and rollback.
- Verify the uninstall entry, Settings uninstall flow, and user-data retention.

A successful CI package build is not a substitute for the clean-machine install/update test.
