"""
job_engine — Job Engine
===================================
Core package for the job scraping, matching, and dashboard system.

Provides:
- config: Environment-driven configuration (.env + defaults)
- models: SQLAlchemy ORM models (Job, Application, ScraperLog, TaxonomyTerm, etc.)
- database: Async DB helpers (get_session, init_db, save_jobs)
- skill_scorer: Profile-to-job matching engine (JobMatcher)
- taxonomy: Canonical skill/value registry (TaxonomyResolver)
"""

from job_engine._sanitize import SANITIZE_FORBIDDANCE, sanitize_job_posting
from job_engine.config import config as _jc
from job_engine.drafter_reviewer import generate_with_review, verify_ats
from job_engine.plugin import PluginBase, PluginRegistry, plugin_registry
from job_engine.reports import get_report, get_report_by_number, get_reports_for_job, save_report
from job_engine.research_budget import (
    ResearchBudget,
    ResearchDepth,
    get_research_budget_from_settings,
)

__version__ = (_jc.project_root / "VERSION").read_text().strip()

__all__ = [
    "sanitize_job_posting",
    "SANITIZE_FORBIDDANCE",
    "generate_with_review",
    "verify_ats",
    "ResearchBudget",
    "ResearchDepth",
    "get_research_budget_from_settings",
    "save_report",
    "get_report",
    "get_report_by_number",
    "get_reports_for_job",
    "PluginBase",
    "PluginRegistry",
    "plugin_registry",
]
