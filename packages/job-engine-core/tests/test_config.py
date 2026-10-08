"""
Tests for the configuration module.
"""

from pathlib import Path

from job_engine.config import JobEngineConfig, config


class TestConfig:
    """Tests for configuration loading."""

    def test_config_is_singleton(self):
        """Config should be a singleton instance."""
        from job_engine.config import config as c2

        assert config is c2

    def test_config_has_defaults(self):
        """Config should have sensible defaults."""
        assert isinstance(config.project_root, Path)
        assert config.project_root.exists()

    def test_config_data_dir_default(self):
        """data_dir should default to <project-root>/data."""
        assert str(config.data_dir).endswith("data")
        assert config.data_dir.exists()

    def test_config_port_default(self):
        """Default port should be 8000."""
        assert config.port == 8000

    def test_config_database_url(self):
        """Database URL should be set."""
        assert "sqlite" in config.database_url
        assert "aiosqlite" in config.database_url

    def test_config_all_json_path(self):
        """All JSON path should point to scrapers output."""
        assert "scraper-output" in str(config.all_json_path)
        assert "_all.json" in str(config.all_json_path)

    def test_config_database_sync_url(self):
        """Sync URL should strip +aiosqlite."""
        sync_url = config.database_sync_url
        assert "+aiosqlite" not in sync_url
        assert "sqlite" in sync_url

    def test_config_job_output_path(self):
        """job_output_path should return correct path."""
        p = config.job_output_path("test")
        assert "test.json" in str(p)

    def test_config_custom_values(self, monkeypatch):
        """Config should respect environment variables when constructed fresh."""
        monkeypatch.setenv("PORT", "9000")
        custom = JobEngineConfig()
        assert custom.port == 9000


class TestProfileSplit:
    """Tests for the profile-split file references (my_cv.md etc.)."""

    def test_cv_style_rules_paths_resolve(self, tmp_path):
        """Provider should expose cv/style/rules file paths under the profile dir."""
        import yaml
        from job_engine.config import ProfileConfig

        profile = tmp_path / "my_profile.yaml"
        profile.write_text(yaml.safe_dump({"name": "Test"}), encoding="utf-8")
        (tmp_path / "my_cv.md").write_text("# CV", encoding="utf-8")
        (tmp_path / "my_style.md").write_text("tone: direct", encoding="utf-8")
        (tmp_path / "my_rules.md").write_text("never fabricate", encoding="utf-8")

        pc = ProfileConfig(yaml_path=profile)
        assert pc.cv_file == tmp_path / "my_cv.md"
        assert pc.style_file == tmp_path / "my_style.md"
        assert pc.rules_file == tmp_path / "my_rules.md"
        assert pc.load_cv() == "# CV"
        assert pc.load_style() == "tone: direct"
        assert pc.load_rules() == "never fabricate"

    def test_explicit_cv_file_ref_overrides_default(self, tmp_path):
        """An explicit cv_file reference in the YAML is honored over the default path."""
        import yaml
        from job_engine.config import ProfileConfig

        profile = tmp_path / "my_profile.yaml"
        profile.write_text(
            yaml.safe_dump({"name": "Test", "cv_file": "cv/alt_cv.md"}), encoding="utf-8"
        )
        (tmp_path / "cv").mkdir()
        (tmp_path / "cv" / "alt_cv.md").write_text("ALT CV", encoding="utf-8")

        pc = ProfileConfig(yaml_path=profile)
        assert pc.cv_file == tmp_path / "cv" / "alt_cv.md"
        assert pc.load_cv() == "ALT CV"
