# Repository, versioning and automatic releases

## Source of truth

- `ori_metadata.py` owns `APP_VERSION`.
- The UI imports that same value. The updater also reads it from `ori_metadata.py`.
- Never hardcode a separate application version in another module.

## Version policy

Use stable SemVer `MAJOR.MINOR.PATCH`:

- Bug fix / reliability fix: increment PATCH (for example, 3.5.0 → 3.5.1 → 3.5.2).
- Backward-compatible feature group: increment MINOR and reset PATCH (for example, 3.5.2 → 3.6.0).
- Breaking compatibility change: increment MAJOR and reset MINOR/PATCH (for example, 3.6.0 → 4.0.0).

For every bug-fix update that is ready to publish, bump `APP_VERSION` in the same PR as the code fix. Do not bump the version for unfinished or failed changes.

## Automatic release flow

1. Code is edited directly in the GitHub repository on a dedicated branch. No repository ZIP download/upload is required for source changes.
2. A PR is tested: compile, pytest, Ruff, Gitleaks and the Windows package smoke test.
3. The PR is merged into `main`.
4. The release workflow reads `APP_VERSION`, compares it to the latest GitHub Release and does nothing if the version has not increased.
5. When the version is newer, GitHub Actions verifies the source again, builds the Windows one-folder app, wraps it in the per-user Inno Setup installer, and publishes `ORI-Setup-<version>.exe` plus its `.sha256` sidecar as release/tag `v<version>`.
6. The installed ORI updater uses one progressive button: Check for Updates → Download Update → Install & Restart. Downloads occur only after the user's click; SHA-256 is verified before installation is offered.

A normal merge that does not bump the version must not publish another release. Failed tests must never publish a release.

## User's part

For an already installed packaged ORI, the user does not need to download the repository or manually upload files. Setup-managed ORI 3.6.3 and later use the single progressive About & Updates button. Users on 3.6.0 or 3.6.1 should install the official 3.6.2-or-later Setup manually once to bootstrap the version-aware updater. The updater requires internet access. Source/development runs do not automatically replace their own files.

## CI and release workflow

- `.github/workflows/ci.yml` runs compilation, tests, Ruff and Gitleaks, and produces a Windows package smoke-test artifact.
- `.github/workflows/release.yml` publishes a new stable release after a successful main-branch merge only when `APP_VERSION` is newer than the latest stable GitHub Release.
- The release workflow is triggered only after the main-branch `ORI CI` workflow succeeds. It builds from that exact tested commit and skips publication if the version has not increased.

## Safety and release integrity

- Do not publish incomplete changes or increment versions for failed fixes.
- Keep user API keys and local memory out of releases.
- The published Setup executable is the single-file user-facing installer and contains the complete Windows app payload, including its runtime.
- Verify third-party license and redistribution terms before public binary distribution.


## In-app update stages

The installed Settings page exposes three separate actions:

1. The one Settings button starts as **Check for Updates** and queries GitHub metadata without downloading.
2. When a release is available, it changes to **Download Update**. The click downloads the versioned Setup EXE and SHA-256 sidecar into `%LOCALAPPDATA%/ORI/updates/<version>`; a mismatch discards the installer.
3. After verification, confirm **Open Update Assistant**. The separate Windows assistant remains visible while ORI closes and Setup installs the new version. It verifies the Windows version registration, then enables **Launch ORI**. After launch, it checks the startup token, process ID, reported version, executable path and 15-second stability before removing the previous-build backup.

Personal settings, API credentials, memory, logs and downloads live outside the program directory and must remain intact through update and uninstall. Helper transcripts are stored under `%LOCALAPPDATA%/ORI/updates/install-helper`.

The in-app update requires a Setup-managed Windows installation. Portable ZIP builds must install the official Setup once before they can use the staged updater. Setup-managed 3.6.0 and 3.6.1 builds must install the official 3.6.2-or-later Setup manually once to replace their older bundled updater helper.

## CI and release verification

- `.github/workflows/ci.yml` runs source compilation, pytest, Ruff and Gitleaks.
- The Windows package job builds the single Setup EXE, verifies its bundled runtime, tests a clean install/uninstall, and exercises an in-place upgrade from the published v3.6.2 Setup to the newly built candidate. The upgrade test checks startup acknowledgement, the installed version and preservation of user data.
- `.github/workflows/release.yml` publishes a stable release only after tests pass and only when `APP_VERSION` is newer than the latest stable release.

## Legacy portable builds

The staged in-app updater is supported by Setup-managed Windows installs. Users still running a portable ZIP build from before v3.6.0 must install a current official Setup manually once. Keep the old portable folder until the new installation opens successfully and its API key and memory have been checked; do not assume an arbitrary old folder is auto-discovered.
