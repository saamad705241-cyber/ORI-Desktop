# Repository and release updates

## Configure the official repository

After creating the public/private GitHub repository, set `github_repository` in the local `config/api_keys.json` to `OWNER/REPOSITORY`. Do not put a GitHub token in this file. Public release checks use GitHub's public Releases API.

## CI

`.github/workflows/ci.yml` runs Python compilation, tests, Ruff correctness checks and Gitleaks on pushes and pull requests.

## Windows package validation

Every CI run builds the one-folder Windows application after tests and secret scanning pass.
The package smoke test verifies `ORI.exe` plus the Phone Remote page, login page, bundled
CryptoJS browser library and its MIT license. CI uploads the verified folder as a short-lived
workflow artifact for manual testing. This validation artifact is not a published ORI release
and does not change the in-app updater's latest-release channel.

## Publishing a Windows release

1. Verify the upstream and third-party license terms before distribution.
2. Update `APP_VERSION` in `ori_metadata.py` and `APP_VERSION` in `ui.py`.
3. Run the test suite and build `dist/ORI` on Windows.
4. Commit and push; create a matching tag such as `v3.5.0`.
5. `.github/workflows/release.yml` builds the one-folder Windows app, publishes `ORI-<version>-Windows.zip`, and publishes the matching `.sha256` sidecar.
6. The in-app updater checks for the latest published release, downloads the ZIP and checksum, verifies SHA-256, and stages the package. Packaged Windows builds can schedule replacement after ORI closes. Source/development builds are never overwritten automatically.

A repository URL is intentionally not guessed or hard-coded before the owner creates it.
