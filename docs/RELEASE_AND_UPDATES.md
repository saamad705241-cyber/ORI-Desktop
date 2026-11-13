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
5. When the version is newer, GitHub Actions verifies the source again, builds the Windows one-folder app, creates `ORI-<version>-Windows.zip` and its SHA-256 sidecar, and publishes a release/tag `v<version>`.
6. The existing ORI updater checks the latest GitHub Release, downloads the ZIP and checksum, verifies SHA-256, stages the update and installs/restarts the packaged Windows build.

A normal merge that does not bump the version must not publish another release. Failed tests must never publish a release.

## User's part

For an already installed packaged ORI, the user does not need to download the repository or manually upload files. Once a verified release is published, the user uses ORI's existing About & Updates controls to check, download and install it. The updater requires internet access. Source/development runs do not automatically replace their own files.

## CI and release workflow

- `.github/workflows/ci.yml` runs compilation, tests, Ruff and Gitleaks, and produces a Windows package smoke-test artifact.
- `.github/workflows/release.yml` publishes a new stable release after a successful main-branch merge only when `APP_VERSION` is newer than the latest stable GitHub Release.
- Manual version tags remain supported, but the tag must match `APP_VERSION`.

## Safety and release integrity

- Do not publish incomplete changes or increment versions for failed fixes.
- Keep user API keys and local memory out of releases.
- The release ZIP contains the full app folder; the final single-file installer and uninstaller remain a separate last phase.
- Verify third-party license and redistribution terms before public binary distribution.


## Windows self-update installation helper

The packaged update installer is copied to `%LOCALAPPDATA%/ORI/updates/install-helper` before ORI exits. It writes a transcript log there, waits up to 120 seconds for the current process to close, backs up the existing program files, copies the staged package while excluding user-data folders and `api_keys.json`, compares the staged and installed `ORI.exe` SHA-256 values, and starts the new executable. If copying, verification or immediate startup fails, it attempts to restore and restart the previous build. The UI reports the log path; a completed download or a started helper is not itself reported as a completed installation.
