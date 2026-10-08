#!/usr/bin/env python3
"""Doctor — Health Check Script.

Runs a comprehensive suite of health checks on the Job Engine installation.
Exit codes:
    0  All checks pass (possibly with warnings)
    1  Warnings (non-critical issues found)
    2  Fatal errors (critical issues found)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


# ── Terminal colour support ───────────────────────────────────────────────────

def _supports_color() -> bool:
    """Return True if the terminal supports ANSI colour codes."""
    if os.environ.get("FORCE_COLOR"):
        return True
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


_USE_COLOR = _supports_color()


def _green(text: str) -> str:
    return f"\033[92m{text}\033[0m" if _USE_COLOR else text


def _yellow(text: str) -> str:
    return f"\033[93m{text}\033[0m" if _USE_COLOR else text


def _red(text: str) -> str:
    return f"\033[91m{text}\033[0m" if _USE_COLOR else text


def _bold(text: str) -> str:
    return f"\033[1m{text}\033[0m" if _USE_COLOR else text


# ── Check result helpers ──────────────────────────────────────────────────────

class CheckResult:
    """Collects results from all checks."""

    def __init__(self) -> None:
        self.passes: list[str] = []
        self.warnings: list[str] = []
        self.errors: list[str] = []

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0

    def ok(self, msg: str) -> None:
        self.passes.append(msg)
        print(f"  {_green('✓')} {msg}")

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)
        print(f"  {_yellow('⚠')} {msg}")

    def err(self, msg: str) -> None:
        self.errors.append(msg)
        print(f"  {_red('✗')} {msg}")

    def summary(self) -> None:
        total = len(self.passes) + len(self.warnings) + len(self.errors)
        print()
        if not self.has_errors and not self.has_warnings:
            print(_green(f"All {total} checks passed."))
        elif self.has_errors:
            print(_red(f"{len(self.errors)} error(s), {len(self.warnings)} warning(s), {len(self.passes)} passed"))
        else:
            print(_yellow(f"{len(self.warnings)} warning(s), {len(self.passes)} passed"))


# ── Project root discovery ────────────────────────────────────────────────────

def _find_project_root() -> Path:
    """Discover project root using the same logic as config.py."""
    if env_root := os.getenv("JOB_ENGINE_ROOT"):
        return Path(env_root)
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if (parent / ".project-root").exists():
            return parent
    scripts_dir = Path(__file__).resolve().parent
    if (scripts_dir.parent / ".project-root").exists():
        return scripts_dir.parent
    return Path.cwd()


_PROJECT_ROOT = _find_project_root()
_DATA_DIR = _PROJECT_ROOT / "data"


# ── Individual checks ─────────────────────────────────────────────────────────

def check_python_version(result: CheckResult) -> None:
    """Check Python >= 3.10."""
    v = sys.version_info
    if v.major >= 3 and v.minor >= 10:
        result.ok(f"Python {v.major}.{v.minor}.{v.micro} (≥3.10)")
    else:
        result.err(f"Python {v.major}.{v.minor}.{v.micro} (need ≥3.10)")


def check_node_version(result: CheckResult) -> None:
    """Check Node.js >= 18 via subprocess."""
    try:
        out = subprocess.check_output(["node", "--version"], text=True, timeout=10).strip()
        ver_str = out.lstrip("v")
        parts = [int(p) for p in ver_str.split(".")]
        if parts[0] >= 18:
            result.ok(f"Node.js {out} (≥18)")
        else:
            result.err(f"Node.js {out} (need ≥18)")
    except FileNotFoundError:
        result.err("Node.js not found on PATH")
    except subprocess.TimeoutExpired:
        result.err("Node.js version check timed out")
    except Exception as e:
        result.err(f"Node.js check failed: {e}")


def check_profile_yaml(result: CheckResult) -> None:
    """Check data/my_profile.yaml exists and is valid YAML."""
    path = _DATA_DIR / "my_profile.yaml"
    if not path.exists():
        result.err("data/my_profile.yaml not found")
        return
    try:
        import yaml  # type: ignore[import-untyped]
        with path.open("r") as f:
            data = yaml.safe_load(f)
        if data is None:
            result.warn("data/my_profile.yaml is empty (no data)")
        elif not isinstance(data, dict):
            result.warn(f"data/my_profile.yaml is not a mapping (got {type(data).__name__})")
        else:
            keys = list(data.keys())
            result.ok(f"data/my_profile.yaml — valid YAML ({len(keys)} top-level keys)")
    except ImportError:
        result.warn("PyYAML not installed — cannot validate profile YAML")
    except Exception as e:
        result.err(f"data/my_profile.yaml parse error: {e}")


def check_scraper_config(result: CheckResult) -> None:
    """Check data/scraper_config.yaml exists."""
    path = _DATA_DIR / "scraper_config.yaml"
    if path.exists():
        result.ok("data/scraper_config.yaml found")
    else:
        result.err("data/scraper_config.yaml not found")


def check_active_scrapers(result: CheckResult) -> None:
    """Check data/active-scrapers/ directory exists."""
    path = _DATA_DIR / "active-scrapers"
    if path.is_dir():
        items = [p for p in path.iterdir() if p.is_dir()]
        result.ok(f"data/active-scrapers/ found ({len(items)} scraper(s))")
    else:
        result.err("data/active-scrapers/ not found")


def check_database(result: CheckResult) -> None:
    """Check data/job_engine.db exists, is readable, and passes integrity check."""
    path = _DATA_DIR / "job_engine.db"
    if not path.exists():
        result.err("data/job_engine.db not found")
        return
    if not os.access(str(path), os.R_OK):
        result.err("data/job_engine.db exists but is not readable")
        return
    result.ok("data/job_engine.db exists and readable")

    try:
        from sqlalchemy import create_engine, text
        db_url = f"sqlite:///{path}"
        engine = create_engine(db_url)
        with engine.connect() as conn:
            row = conn.execute(text("PRAGMA integrity_check")).fetchone()
        if row and row[0] == "ok":
            result.ok("SQLite integrity check passed")
        else:
            result.err(f"SQLite integrity check failed: {row[0] if row else 'unknown'}")
        engine.dispose()
    except ImportError:
        result.warn("SQLAlchemy not installed — cannot run DB integrity check")
    except Exception as e:
        result.err(f"Database integrity check failed: {e}")


def check_env_file(result: CheckResult) -> None:
    """Check config/.env exists (secrets + environment overrides)."""
    if (_PROJECT_ROOT / "config" / ".env").exists():
        result.ok("config/.env found")
    else:
        result.warn("config/.env not found — copy from config/.env.example")


def check_llm_api_key(result: CheckResult) -> None:
    """Check an LLM API key is configured; without one, AI features are disabled."""
    try:
        from job_engine.llm import has_api_key
    except ImportError as e:
        result.warn(f"Cannot check LLM API key — job_engine.llm import failed: {e}")
        return
    if has_api_key():
        result.ok("LLM API key configured")
    else:
        result.warn("No LLM API key configured — AI features disabled")


def check_imports(result: CheckResult) -> None:
    """Try to import key Python packages."""
    checks: list[tuple[str, str]] = [
        ("job_engine", "Core package"),
        ("job_engine.config", "Configuration module"),
        ("job_engine.models", "SQLAlchemy models"),
        ("job_engine.database", "Database helpers"),
        ("job_engine.skill_scorer", "Matching engine"),
        ("job_engine.llm", "LLM module"),
        ("job_engine.scraper_config", "Scraper configuration"),
        ("job_engine.currency_converter", "Currency converter"),
    ]
    for module, label in checks:
        try:
            __import__(module, fromlist=["__dummy__"])
            result.ok(f"Import {module} — {label}")
        except ImportError as e:
            result.err(f"Import {module} failed: {e}")
        except Exception as e:
            result.err(f"Import {module} raised: {e}")


def check_node_dependencies(result: CheckResult) -> None:
    """Check Node.js package dependencies exist."""
    node_modules = _PROJECT_ROOT / "packages" / "job-engine-scrapers" / "node_modules"
    if node_modules.is_dir():
        pkg_count = sum(1 for p in node_modules.iterdir() if p.is_dir() and not p.name.startswith("."))
        if pkg_count > 0:
            result.ok(f"Node.js dependencies installed ({pkg_count} packages in node_modules)")
        else:
            result.warn("node_modules exists but appears empty")
    else:
        result.err("Node.js dependencies not found (packages/job-engine-scrapers/node_modules)")


def check_disk_space(result: CheckResult) -> None:
    """Check available disk space for the data directory."""
    try:
        usage = shutil.disk_usage(_DATA_DIR)
        free_gb = usage.free / (1024 ** 3)
        if free_gb < 0.1:
            result.err(f"Low disk space: {free_gb:.1f} GB free")
        elif free_gb < 0.5:
            result.warn(f"Disk space: {free_gb:.1f} GB free")
        else:
            result.ok(f"Disk space: {free_gb:.1f} GB free")
    except Exception as e:
        result.warn(f"Could not check disk space: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    print()
    print(_bold(f"Job Engine Health Check — {_PROJECT_ROOT.name}"))
    print(f"  Project root: {_PROJECT_ROOT}")
    print(f"  Data dir:     {_DATA_DIR}")
    if _USE_COLOR:
        print(f"  Terminal:     colour enabled")
    print()

    result = CheckResult()

    check_python_version(result)
    check_node_version(result)
    check_env_file(result)
    check_profile_yaml(result)
    check_scraper_config(result)
    check_active_scrapers(result)
    check_database(result)
    check_imports(result)
    check_llm_api_key(result)
    check_node_dependencies(result)
    check_disk_space(result)

    result.summary()
    print()

    if result.has_errors:
        return 2
    if result.has_warnings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
