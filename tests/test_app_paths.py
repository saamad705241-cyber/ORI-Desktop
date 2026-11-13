from pathlib import Path

from core import app_paths


def test_source_run_keeps_data_in_project_root():
    assert app_paths.get_app_data_dir() == Path(__file__).resolve().parents[1]


def test_legacy_data_migration_preserves_config_memory_and_user_folders(tmp_path):
    install = tmp_path / "portable"
    data = tmp_path / "LocalAppData" / "ORI"
    (install / "config").mkdir(parents=True)
    (install / "memory").mkdir()
    (install / "downloads").mkdir()
    (install / "config" / "api_keys.json").write_text('{"gemini_api_key":"old"}', encoding="utf-8")
    (install / "memory" / "long_term.json").write_text('{"identity":{}}', encoding="utf-8")
    (install / "downloads" / "clip.txt").write_text("keep", encoding="utf-8")

    (data / "config").mkdir(parents=True)
    (data / "config" / "api_keys.json").write_text('{"gemini_api_key":"new"}', encoding="utf-8")

    app_paths._migrate_legacy_data(install, data)

    assert (data / "config" / "api_keys.json").read_text(encoding="utf-8") == '{"gemini_api_key":"new"}'
    assert (data / "memory" / "long_term.json").is_file()
    assert (data / "downloads" / "clip.txt").read_text(encoding="utf-8") == "keep"


def test_second_migration_merges_only_missing_files(tmp_path):
    install = tmp_path / "portable"
    data = tmp_path / "data"
    (install / "logs").mkdir(parents=True)
    (install / "logs" / "old.log").write_text("legacy", encoding="utf-8")
    (data / "logs").mkdir(parents=True)
    (data / "logs" / "new.log").write_text("current", encoding="utf-8")

    app_paths._migrate_legacy_data(install, data)

    assert (data / "logs" / "old.log").read_text(encoding="utf-8") == "legacy"
    assert (data / "logs" / "new.log").read_text(encoding="utf-8") == "current"
