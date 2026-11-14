from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_release_workflow_skips_ci_from_a_stale_main_commit():
    source = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "branches/main" in source
    assert "$currentMainSha -ne $env:SOURCE_SHA" in source
    assert '"release_needed=false"' in source
    assert "Skipping stale release candidate" in source


def test_release_workflow_builds_setup_and_sha256_for_the_committed_app_version():
    source = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert 'python -c "from ori_metadata import APP_VERSION; print(APP_VERSION)"' in source
    assert '"/DMyAppVersion=$env:ORI_VERSION"' in source
    assert 'ORI-Setup-\${{ needs.verify.outputs.app_version }}.exe.sha256' in source
