"""Tests for resolved_project_slug() method and its consumers."""

from stokowski.config import (
    ServiceConfig,
    TrackerConfig,
    validate_config,
)


class TestResolvedProjectSlug:
    """Tests for ServiceConfig.resolved_project_slug()."""

    def test_literal_value_from_yaml(self):
        """Should return literal project_slug from YAML."""
        cfg = ServiceConfig()
        cfg.tracker = TrackerConfig(project_slug="abc123")
        assert cfg.resolved_project_slug() == "abc123"

    def test_empty_slug_falls_back_to_env_var(self, monkeypatch):
        """Should fall back to LINEAR_PROJECT_SLUG env var when YAML is empty."""
        monkeypatch.setenv("LINEAR_PROJECT_SLUG", "env-slug-456")
        cfg = ServiceConfig()
        cfg.tracker = TrackerConfig(project_slug="")
        assert cfg.resolved_project_slug() == "env-slug-456"

    def test_yaml_value_takes_precedence_over_env(self, monkeypatch):
        """YAML literal should win over LINEAR_PROJECT_SLUG env var."""
        monkeypatch.setenv("LINEAR_PROJECT_SLUG", "env-slug-456")
        cfg = ServiceConfig()
        cfg.tracker = TrackerConfig(project_slug="yaml-slug")
        assert cfg.resolved_project_slug() == "yaml-slug"

    def test_dollar_var_reference_resolved(self, monkeypatch):
        """$VAR reference in project_slug should be resolved from env."""
        monkeypatch.setenv("MY_PROJECT_SLUG", "resolved-from-var")
        cfg = ServiceConfig()
        cfg.tracker = TrackerConfig(project_slug="$MY_PROJECT_SLUG")
        assert cfg.resolved_project_slug() == "resolved-from-var"

    def test_dollar_var_takes_precedence_over_linear_project_slug(self, monkeypatch):
        """$VAR reference should win over LINEAR_PROJECT_SLUG fallback."""
        monkeypatch.setenv("MY_PROJECT_SLUG", "from-dollar-var")
        monkeypatch.setenv("LINEAR_PROJECT_SLUG", "from-fallback")
        cfg = ServiceConfig()
        cfg.tracker = TrackerConfig(project_slug="$MY_PROJECT_SLUG")
        assert cfg.resolved_project_slug() == "from-dollar-var"

    def test_no_yaml_no_env_returns_empty(self, monkeypatch):
        """Should return empty string when neither YAML nor env var is set."""
        monkeypatch.delenv("LINEAR_PROJECT_SLUG", raising=False)
        cfg = ServiceConfig()
        cfg.tracker = TrackerConfig(project_slug="")
        assert cfg.resolved_project_slug() == ""

    def test_unset_dollar_var_falls_back_to_env(self, monkeypatch):
        """If $VAR reference points to an unset var, fall back to LINEAR_PROJECT_SLUG."""
        monkeypatch.delenv("NONEXISTENT_VAR", raising=False)
        monkeypatch.setenv("LINEAR_PROJECT_SLUG", "fallback-slug")
        cfg = ServiceConfig()
        cfg.tracker = TrackerConfig(project_slug="$NONEXISTENT_VAR")
        # _resolve_env returns "" for unset var, then env fallback kicks in
        assert cfg.resolved_project_slug() == "fallback-slug"


class TestValidateConfigProjectSlug:
    """Tests for validate_config() with resolved_project_slug()."""

    def test_missing_slug_reports_error(self, monkeypatch):
        """Should report error when neither YAML slug nor env var is set."""
        monkeypatch.delenv("LINEAR_PROJECT_SLUG", raising=False)
        cfg = ServiceConfig()
        cfg.tracker = TrackerConfig(project_slug="")
        errors = validate_config(cfg, skip_secrets_check=True)
        assert any("project_slug" in e.lower() for e in errors)

    def test_env_var_satisfies_slug_validation(self, monkeypatch):
        """Should not report error when LINEAR_PROJECT_SLUG is set even without YAML."""
        monkeypatch.setenv("LINEAR_PROJECT_SLUG", "from-env")
        cfg = ServiceConfig()
        cfg.tracker = TrackerConfig(project_slug="")
        errors = validate_config(cfg, skip_secrets_check=True)
        slug_errors = [e for e in errors if "project_slug" in e.lower()]
        assert slug_errors == []

    def test_yaml_slug_satisfies_validation(self):
        """Should not report error when project_slug is in YAML."""
        cfg = ServiceConfig()
        cfg.tracker = TrackerConfig(project_slug="from-yaml")
        errors = validate_config(cfg, skip_secrets_check=True)
        slug_errors = [e for e in errors if "project_slug" in e.lower()]
        assert slug_errors == []


class TestAgentEnvProjectSlug:
    """Tests for ServiceConfig.agent_env() with resolved_project_slug()."""

    def test_agent_env_includes_yaml_slug(self):
        """agent_env should include LINEAR_PROJECT_SLUG from YAML value."""
        cfg = ServiceConfig()
        cfg.tracker = TrackerConfig(project_slug="yaml-slug")
        env = cfg.agent_env()
        assert env["LINEAR_PROJECT_SLUG"] == "yaml-slug"

    def test_agent_env_includes_env_fallback_slug(self, monkeypatch):
        """agent_env should include LINEAR_PROJECT_SLUG from env var fallback."""
        monkeypatch.setenv("LINEAR_PROJECT_SLUG", "env-slug")
        cfg = ServiceConfig()
        cfg.tracker = TrackerConfig(project_slug="")
        env = cfg.agent_env()
        assert env["LINEAR_PROJECT_SLUG"] == "env-slug"

    def test_agent_env_yaml_overrides_env(self, monkeypatch):
        """agent_env should use YAML value over env var fallback."""
        monkeypatch.setenv("LINEAR_PROJECT_SLUG", "env-slug")
        cfg = ServiceConfig()
        cfg.tracker = TrackerConfig(project_slug="yaml-slug")
        env = cfg.agent_env()
        assert env["LINEAR_PROJECT_SLUG"] == "yaml-slug"
