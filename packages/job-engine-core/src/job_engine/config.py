"""
Configuration module for the Job Engine.

Loads settings from .env file with sensible defaults.
All paths are relative to the project root directory.
"""

import logging
import os
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


# Discover project root: JOB_ENGINE_ROOT env var, or walk up for .project-root sentinel.
def _discover_project_root() -> Path:
    if env_root := os.getenv("JOB_ENGINE_ROOT"):
        return Path(env_root)
    # Walk up from this file looking for .project-root sentinel
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if (parent / ".project-root").exists():
            return parent
    # Fallback: use CWD (works for CLI usage)
    return Path.cwd()


_PROJECT_ROOT = _discover_project_root()
load_dotenv(_PROJECT_ROOT / "config" / ".env")


logger = logging.getLogger(__name__)


def _resolve_data_dir() -> Path:
    raw = os.getenv("DATA_DIR", "data")
    p = Path(raw)
    if p.is_absolute():
        return p
    return _PROJECT_ROOT / p


def _bool(val: str | None, default: bool = False) -> bool:
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _safe_int(val: str | None, default: int) -> int:
    """Parse an int from env var, returning default on failure."""
    if val is None:
        return default
    try:
        return int(val.strip())
    except (ValueError, TypeError):
        warnings.warn(f"Invalid integer in env var, using default {default}: '{val}'")
        return default


@dataclass(frozen=True)
class JobEngineConfig:
    """Immutable configuration holding all environment-driven settings."""

    # ── Paths ────────────────────────────────────────────────────────────────
    project_root: Path = _PROJECT_ROOT
    data_dir: Path = field(default_factory=_resolve_data_dir)

    # ── Dashboard ───────────────────────────────────────────────────────────
    port: int = field(default_factory=lambda: _safe_int(os.getenv("PORT"), 8000))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper())

    # ── Proxy (optional) ────────────────────────────────────────────────────
    http_proxy: str = field(default_factory=lambda: os.getenv("HTTP_PROXY", ""))
    https_proxy: str = field(default_factory=lambda: os.getenv("HTTPS_PROXY", ""))

    def __post_init__(self):
        """Validate config after initialization."""
        profile = object.__getattribute__(self, "profile_path")
        if not profile.exists():
            warnings.warn(f"Profile not found at {profile}. Scoring will fail until it exists.")

    # ── Derived properties ──────────────────────────────────────────────────

    @property
    def database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.data_dir / 'job_engine.db'}"

    @property
    def database_sync_url(self) -> str:
        """Return a sync SQLAlchemy URL (strips +aiosqlite)."""
        return self.database_url.replace("+aiosqlite", "")

    @property
    def profile_path(self) -> Path:
        return self.data_dir / "my_profile.yaml"

    @property
    def scraper_output_dir(self) -> Path:
        return self.data_dir / "scraper-output"

    @property
    def all_json_path(self) -> Path:
        return self.scraper_output_dir / "_all.json"

    def job_output_path(self, name: str) -> Path:
        """Return path for a named scraper's output JSON."""
        return self.scraper_output_dir / f"{name}.json"


# ── Profile Configuration ──────────────────────────────────────────────────


class ProfileConfig:
    """Read/write the full my_profile.yaml with ruamel round-trip.

    Follows the same pattern as scraper_config.py: uses ruamel.yaml round-trip
    loader to preserve comments, formatting, and key order on save.

    Usage:
        config = ProfileConfig()
        profile = config.load()           # full dict
        config.update_section("rate", {"min_monthly": 30000, ...})
    """

    def __init__(self, yaml_path: Path | None = None) -> None:
        from ruamel.yaml import YAML

        self._yaml_path = yaml_path or config.data_dir / "my_profile.yaml"
        self._yaml = YAML()
        self._yaml.preserve_quotes = True
        self._yaml.indent(mapping=2, sequence=4, offset=2)

    # ── Profile file paths ──────────────────────────────────────────────────

    @property
    def cv_path(self) -> Path:
        """Default path for the canonical CV (my_cv.md next to the profile)."""
        return self._yaml_path.parent / "my_cv.md"

    @property
    def style_path(self) -> Path:
        """Default path for the writing style guide (my_style.md)."""
        return self._yaml_path.parent / "my_style.md"

    @property
    def rules_path(self) -> Path:
        """Default path for the procedural rules file (my_rules.md)."""
        return self._yaml_path.parent / "my_rules.md"

    def _referenced_path(self, key: str, default: Path) -> Path:
        """Resolve a profile-split file path from my_profile.yaml.

        Honors a per-file reference key (``cv_file`` / ``style_file`` /
        ``rules_file``) in the profile YAML. Relative references are resolved
        against the profile's directory; an explicit reference that points at a
        file overrides the default sibling path.
        """
        data = self.load()
        ref = data.get(key)
        if isinstance(ref, str) and ref.strip():
            candidate = Path(ref)
            if not candidate.is_absolute():
                candidate = self._yaml_path.parent / candidate
            return candidate
        return default

    @property
    def cv_file(self) -> Path:
        """Path to the canonical CV, honoring the ``cv_file`` YAML ref."""
        return self._referenced_path("cv_file", self.cv_path)

    @property
    def style_file(self) -> Path:
        """Path to the style guide, honoring the ``style_file`` YAML ref."""
        return self._referenced_path("style_file", self.style_path)

    @property
    def rules_file(self) -> Path:
        """Path to the rules file, honoring the ``rules_file`` YAML ref."""
        return self._referenced_path("rules_file", self.rules_path)

    def load_cv(self) -> str:
        """Return the CV content, or empty string if not found."""
        path = self.cv_file
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def load_style(self) -> str:
        """Return the style guide content, or empty string if not found."""
        path = self.style_file
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    def load_rules(self) -> str:
        """Return the rules content, or empty string if not found."""
        path = self.rules_file
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    # ── Public API ────────────────────────────────────────────────────────

    def load(self) -> dict[str, Any]:
        """Return the full profile as a dict."""
        if not self._yaml_path.exists():
            logger.warning("Profile file not found at %s", self._yaml_path)
            return {}
        with self._yaml_path.open("r", encoding="utf-8") as fh:
            data = self._yaml.load(fh) or {}
        return dict(data)

    def save(self, data: dict[str, Any]) -> None:
        """Write the full profile dict to YAML, preserving formatting."""
        with self._yaml_path.open("w", encoding="utf-8") as fh:
            self._yaml.dump(data, fh)

    def update_section(self, section: str, values: Any) -> dict[str, Any]:
        """Load, update one top-level key, write, return the full updated profile.

        Args:
            section: Top-level key in the profile YAML (e.g. ``"skills"``).
            values: The new value to assign (dict, list, scalar, etc.).

        Returns:
            The complete updated profile dict.
        """
        data = self.load()
        data[section] = values
        self.save(data)
        return data


# Lazy-init singleton
_profile_config_instance: ProfileConfig | None = None


def get_profile_config() -> ProfileConfig:
    """Lazy-init singleton."""
    global _profile_config_instance
    if _profile_config_instance is None:
        _profile_config_instance = ProfileConfig()
    return _profile_config_instance


# Singleton — importers get the same instance
config: JobEngineConfig = JobEngineConfig()

# ── App Settings Configuration ──────────────────────────────────────────────


class AppSettings:
    """Read/write data/app_settings.yaml with ruamel round-trip.

    Stores app-level settings (LLM config, language, currency) that are
    managed from the dashboard Settings tab, not from the profile.

    The file is created automatically with defaults on first access.

    Usage:
        settings = AppSettings()
        all = settings.load()
        settings.update_section("llm", {"model": "openai/gpt-4o-mini", ...})
    """

    _DEFAULT_PATH = _PROJECT_ROOT / "data" / "app_settings.yaml"

    _DEFAULTS: dict[str, Any] = {
        "llm": {
            "provider": "openrouter",
            "api_key": "",
            "openai_api_key": "",
            "anthropic_api_key": "",
            "model": "openai/gpt-4o-mini",
            "temperature": 0.3,
            "max_tokens": 8192,
            "max_retries": 2,
            "request_timeout": 300,
        },
        "language": "english",
        "currency": "USD",
        "onboarding": {
            "dismissed": False,
        },
    }

    def __init__(self, yaml_path: Path | None = None) -> None:
        from ruamel.yaml import YAML

        self._yaml_path = yaml_path or self._DEFAULT_PATH
        self._yaml = YAML()
        self._yaml.preserve_quotes = True
        self._yaml.indent(mapping=2, sequence=4, offset=2)

        # Seed with defaults if file doesn't exist
        if not self._yaml_path.exists():
            logger.info("Creating default app_settings.yaml at %s", self._yaml_path)
            self._yaml_path.parent.mkdir(parents=True, exist_ok=True)
            self.save(self._DEFAULTS.copy())

    # ── Public API ────────────────────────────────────────────────────────

    def load(self) -> dict[str, Any]:
        """Return the full app settings as a dict."""
        if not self._yaml_path.exists():
            return self._DEFAULTS.copy()
        with self._yaml_path.open("r", encoding="utf-8") as fh:
            data = self._yaml.load(fh) or {}
        return dict(data)

    def save(self, data: dict[str, Any]) -> None:
        """Write the full app settings dict to YAML, preserving formatting."""
        with self._yaml_path.open("w", encoding="utf-8") as fh:
            self._yaml.dump(data, fh)

    def update_section(self, section: str, values: Any) -> dict[str, Any]:
        """Load, update one top-level key, write, return the full updated settings.

        Args:
            section: Top-level key in the settings YAML (e.g. ``"llm"``).
            values: The new value to assign (dict, list, scalar, etc.).

        Returns:
            The complete updated settings dict.
        """
        data = self.load()
        data[section] = values
        self.save(data)
        return data


# Lazy-init singleton
_app_settings_instance: AppSettings | None = None


def get_app_settings() -> AppSettings:
    """Lazy-init singleton for AppSettings."""
    global _app_settings_instance
    if _app_settings_instance is None:
        _app_settings_instance = AppSettings()
    return _app_settings_instance
