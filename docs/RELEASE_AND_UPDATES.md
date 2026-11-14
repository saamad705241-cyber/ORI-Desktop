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
6. The installed ORI updater checks release metadata, downloads the Setup executable and checksum only after the user requests it, verifies SHA-256, and installs/restarts only after the user confirms.

A normal merge that does not bump the version must not publish another release. Failed tests must never publish a release.

## User's part

For an already installed packaged ORI, the user does not need to download the repository or manually upload files. Setup-managed ORI 3.6.2 and later use the version-verified About & Updates flow. Users on 3.6.0 or 3.6.1 must run the current official Setup manually once because those builds contain the older bundled update helper. The updater requires internet access. Source/development runs do not automatically replace their own files.

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

1. **Check for Updates** requests GitHub's latest-release metadata only. It does not download or install anything.
2. **Download Update** downloads the versioned Setup EXE and matching SHA-256 sidecar into `%LOCALAPPDATA%/ORI/updates/<version>`, then verifies the digest. A mismatch discards the installer.
3. **Install Update** is enabled only after a verified download. After explicit user confirmation, a detached PowerShell helper waits for ORI to close, backs up the program directory, runs the Setup EXE in the existing install location, launches the new ORI with a one-time startup token, and waits for the new process to remain alive. A failed install/startup restores the previous program files.

Personal settings, API credentials, memory, logs and downloads live outside the program directory and must remain intact through update and uninstall. Helper transcripts are stored under `%LOCALAPPDATA%/ORI/updates/install-helper`.

The in-app update requires a Setup-managed Windows installation. Portable ZIP builds must install the official Setup once before they can use the staged updater. Setup-managed 3.6.0 and 3.6.1 builds must also install the current Setup manually once to replace their older bundled updater helper.

## CI and release verification

- `.github/workflows/ci.yml` runs source compilation, pytest, Ruff and Gitleaks.
- The Windows package job builds the single Setup EXE, verifies its bundled runtime, tests a clean install/uninstall, and exercises an in-place upgrade from the published v3.6.0 Setup to the newly built candidate. The upgrade test checks startup acknowledgement, the installed version and preservation of user data.
- `.github/workflows/release.yml` publishes a stable release only after tests pass and only when `APP_VERSION` is newer than the latest stable release.

## Legacy portable builds

The staged in-app updater is supported by Setup-managed Windows installs. Users still running a portable ZIP build from before v3.6.0 must install a current official Setup manually once. Keep the old portable folder until the new installation opens successfully and its API key and memory have been checked; do not assume an arbitrary old folder is auto-discovered.
