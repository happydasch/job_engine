"""
SQLAlchemy models for the Job Engine.

Stores scraped job listings, match scores, application tracking,
and scraper run logs using SQLite (aiosqlite for async access).
"""

import json
import logging
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

logger = logging.getLogger(__name__)


def as_utc(dt: datetime | None) -> datetime | None:
    """Return ``dt`` as a UTC-aware datetime (``None`` in, ``None`` out).

    Datetime columns here are written as UTC-aware values, but SQLite drops
    ``tzinfo`` on storage, so values read back from the DB are naive. Re-apply
    UTC rather than letting naive values be interpreted in the host's local
    zone — otherwise aware/naive arithmetic raises ``TypeError`` and a bare
    ``.timestamp()`` call silently shifts by the local UTC offset.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _load_json_list(raw: str | None, field_name: str, job_id: int | None) -> list:
    """Parse a JSON-list column, returning [] for empty or corrupt values."""
    if not raw:
        return []
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Corrupt %s JSON for job %d — returning []", field_name, job_id)
        return []


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums / Constants
# ---------------------------------------------------------------------------

JOB_STATUSES = ("new", "matched", "applied", "interview", "offer", "rejected", "archived")
CONTRACT_TYPES = ("full_time", "part_time", "contract", "freelance", "internship", "other")

# Canonical application lifecycle vocabulary — the single source of truth for
# both the DB constraint below and the status machine in dashboard/routes/applications.py.
APPLICATION_STATUSES = ("applied", "interview", "offer", "accepted", "rejected", "withdrawn")
# Statuses where the search for this job is over (no more interviewing/following up).
APPLICATION_TERMINAL_STATUSES = frozenset({"accepted", "rejected", "withdrawn"})


# ---------------------------------------------------------------------------
# Company
# ---------------------------------------------------------------------------


class Company(Base):
    """A company that posts job listings."""

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="Normalized company name",
    )
    url: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Company website URL")
    logo_url: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Company logo image URL"
    )
    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Company description / about"
    )
    industry: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="Industry sector"
    )
    size_range: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="Employee count range, e.g. '50-200'"
    )
    headquarters: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="HQ location"
    )
    founded_year: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="Year founded")
    linkedin_url: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="LinkedIn company page URL"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    # Relationships
    # NOTE: no ORM cascade on jobs; the FK ON DELETE SET NULL handles DB-level cleanup.
    jobs: Mapped[list["Job"]] = relationship("Job", back_populates="company_rel")

    def __repr__(self) -> str:
        return f"<Company id={self.id} name={self.name!r}>"


# Job Listing
# ---------------------------------------------------------------------------


class Job(Base):
    """A job listing scraped from any platform."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="Platform-unique ID, e.g. 'justjoin_<guid>'",
    )
    platform: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Source platform: justjoin.it, nofluffjobs.com, upwork.com",
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    company_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="FK to companies table",
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Salary
    salary_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="USD")
    contract_type: Mapped[str] = mapped_column(String(20), nullable=False, default="full_time")

    # Secondary salary (alternative contract type like UoP)
    secondary_salary_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    secondary_salary_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    secondary_currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    secondary_contract_type: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Location
    location: Mapped[str] = mapped_column(String(255), nullable=False, default="Remote")
    remote: Mapped[bool] = mapped_column(Boolean, default=False)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Hybrid work flag (separate from remote)
    hybrid: Mapped[bool] = mapped_column(Boolean, default=False)

    # Geo
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    street: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Metadata
    skills: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
        comment="JSON list of skill strings",
    )
    skills_slugs: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
        comment="JSON list of canonical taxonomy slugs for skills",
    )
    category: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    experience_level: Mapped[str] = mapped_column(String(50), nullable=False, default="")

    # Benefits stored as JSON string
    benefits: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="JSON array of benefit strings"
    )

    # Languages as JSON string
    languages: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="JSON array of {code, level} objects"
    )

    # Nice-to-have skills as JSON string
    nice_to_have_skills: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="JSON array of skill strings"
    )

    # Note: contract_time is deprecated, use working_time instead.
    contract_time: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="full_time",
        comment="[deprecated] Use working_time instead — full_time / part_time",
    )

    # Work info
    working_time: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="full_time",
        comment="full_time / part_time / flexible — work schedule",
    )

    # Division/category detail
    division: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Validity dates
    valid_from: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expired_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Application tracking
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="new", index=True)
    match_score: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Match score 0-100"
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # User preferences
    hidden: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="User-dismissed / hidden from list"
    )
    favorite: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="User-favorited / bookmarked"
    )
    fetched_content: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Full page content fetched from the offer URL"
    )

    # LLM analysis
    llm_analysis: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Cached LLM analysis JSON"
    )
    # Cached LLM explain match, cover letter, and questions
    llm_explain_match: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Cached LLM explain-match JSON"
    )
    llm_cover_letter: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Cached LLM cover letter text"
    )
    llm_questions: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Cached LLM interview questions JSON"
    )

    __table_args__ = (
        CheckConstraint("match_score >= 0 AND match_score <= 100", name="ck_job_match_score"),
        CheckConstraint(
            "status IN ({})".format(", ".join(repr(s) for s in JOB_STATUSES)),
            name="ck_job_status",
        ),
        CheckConstraint(
            # contract_type holds the employment contract type from scrapers.
            # Normalized to lowercase. Common values: b2b, permanent/uop, uz, ud,
            # contract, freelance, internship. Working_time (separate column)
            # handles full_time/part_time/flexible.
            "contract_type IN ('b2b', 'permanent', 'uop', 'uz', 'ud', "
            "'full_time', 'part_time', 'contract', 'freelance', 'internship', 'other')",
            name="ck_job_contract_type",
        ),
    )

    # Timestamps
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    # Relationships
    applications: Mapped[list["Application"]] = relationship(
        "Application", back_populates="job", cascade="all, delete-orphan"
    )
    company_rel: Mapped["Company | None"] = relationship("Company", back_populates="jobs")

    # ---- convenience accessors ----

    @property
    def skills_list(self) -> list[str]:
        return _load_json_list(self.skills, "skills", self.id)

    @skills_list.setter
    def skills_list(self, value: list[str]) -> None:
        self.skills = json.dumps(value or [])

    @property
    def skills_slugs_list(self) -> list[str]:
        return _load_json_list(self.skills_slugs, "skills_slugs", self.id)

    @skills_slugs_list.setter
    def skills_slugs_list(self, value: list[str]) -> None:
        self.skills_slugs = json.dumps(value or [])

    @property
    def salary_range(self) -> str:
        if self.salary_min and self.salary_max:
            return f"{self.salary_min:,.0f} - {self.salary_max:,.0f} {self.currency}"
        if self.salary_min:
            return f"from {self.salary_min:,.0f} {self.currency}"
        if self.salary_max:
            return f"up to {self.salary_max:,.0f} {self.currency}"
        return "N/A"

    @property
    def is_remote(self) -> bool:
        return self.remote or "remote" in self.location.lower()

    @property
    def benefits_list(self) -> list[str]:
        return _load_json_list(self.benefits, "benefits", self.id)

    @property
    def languages_list(self) -> list[dict]:
        return _load_json_list(self.languages, "languages", self.id)

    @property
    def nice_to_have_skills_list(self) -> list[str]:
        return _load_json_list(self.nice_to_have_skills, "nice_to_have_skills", self.id)

    @property
    def active_application(self) -> "Application | None":
        """The job's non-deleted application, if one exists (at most one per job)."""
        for app in self.applications:
            if app.deleted_at is None:
                return app
        return None

    def to_dict(self) -> dict:
        """Convert ORM model to a plain dict for the skill scorer and API responses."""

        def _iso(dt: datetime | None) -> str | None:
            return dt.isoformat() if dt else None

        return {
            "id": self.id,
            "external_id": self.external_id,
            "platform": self.platform,
            "title": self.title,
            "company": self.company_rel.name if self.company_rel else "Unknown",
            "company_id": self.company_id,
            "url": self.url,
            "description": self.description,
            "salary_min": self.salary_min,
            "salary_max": self.salary_max,
            "currency": self.currency,
            "contract_type": self.contract_type,
            "location": self.location,
            "remote": self.remote,
            "city": self.city,
            "skills": self.skills_list,
            "skills_slugs": self.skills_slugs_list,
            "category": self.category,
            "experience_level": self.experience_level,
            "match_score": self.match_score,
            "hidden": self.hidden,
            "favorite": self.favorite,
            "status": self.status,
            "application_status": (
                self.active_application.status if self.active_application else None
            ),
            "application_id": (self.active_application.id if self.active_application else None),
            "fetched_content": self.fetched_content,
            "llm_analysis": self.llm_analysis,
            "llm_explain_match": self.llm_explain_match,
            "llm_cover_letter": self.llm_cover_letter,
            "llm_questions": self.llm_questions,
            "discovered_at": _iso(self.discovered_at),
            "updated_at": _iso(self.updated_at),
        }

    def __repr__(self) -> str:
        return (
            f"<Job id={self.id} platform={self.platform} "
            f"title={self.title!r} company={self.company_rel.name if self.company_rel else '?'} "
            f"status={self.status} score={self.match_score}>"
        )


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------


class Application(Base):
    """Tracks the application lifecycle for a job."""

    __tablename__ = "applications"

    __table_args__ = (
        CheckConstraint(
            "status IN ({})".format(", ".join(repr(s) for s in APPLICATION_STATUSES)),
            name="ck_application_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="applied",
        index=True,
        comment="applied → interview → offer → accepted | rejected → withdrawn",
    )
    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, default=lambda: datetime.now(UTC)
    )
    interview_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    offer_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    outcome: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Notes on outcome / rejection reason"
    )
    outcome_reason: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Structured outcome: hired, offer_declined, rejected, no_response, interview_only",
    )
    archived_materials_path: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Path to archived CV/cover letter files"
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="Soft-delete timestamp"
    )
    cover_letter: Mapped[str | None] = mapped_column(Text, nullable=True)

    interview_stages: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default="{}",
        comment=(
            'JSON object: {"phone_screen": bool, "technical": bool, "onsite": bool, "offer": bool}'
        ),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    last_contact_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="Last contact with the employer"
    )

    follow_up_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Number of follow-up contacts recorded for this application",
    )
    follow_up_notes: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Free-form notes on the latest follow-up"
    )

    job: Mapped["Job"] = relationship("Job", back_populates="applications")

    logs: Mapped[list["ApplicationLog"]] = relationship(
        "ApplicationLog", back_populates="application", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Application id={self.id} job_id={self.job_id} status={self.status}>"


# ---------------------------------------------------------------------------
# Application Log (audit trail)
# ---------------------------------------------------------------------------


class ApplicationLog(Base):
    """Append-only audit trail for application status changes."""

    __tablename__ = "application_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    application_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="Previous status, or None on creation"
    )
    to_status: Mapped[str] = mapped_column(String(20), nullable=False, comment="New status")
    changed_by: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="user",
        comment="Who made the change: 'user' or 'system'",
    )
    reason: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Optional reason for the change"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )

    # Relationships
    application: Mapped["Application"] = relationship("Application", back_populates="logs")

    def __repr__(self) -> str:
        return (
            f"<ApplicationLog id={self.id} app_id={self.application_id} "
            f"{self.from_status}→{self.to_status}>"
        )


# ---------------------------------------------------------------------------
# Scraper Run Log
# ---------------------------------------------------------------------------


class ScraperLog(Base):
    """Logs each scraper run for monitoring and debugging."""

    __tablename__ = "scraper_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scraper: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Scraper ID: justjoin_it, nofluffjobs, upwork "
        "(or dashboard_run_<id> aggregate rows)",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="success",
        comment="success / partial / failed",
    )
    jobs_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    jobs_matched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True, comment="JSON metadata")
    run_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )

    def __repr__(self) -> str:
        return (
            f"<ScraperLog id={self.id} scraper={self.scraper} "
            f"status={self.status} jobs={self.jobs_found}>"
        )


# ---------------------------------------------------------------------------
# Taxonomy — canonical skill/value registry
# ---------------------------------------------------------------------------


class TaxonomyTerm(Base):
    """A canonical term in the taxonomy registry.

    Each slug is the canonical identifier for a skill, behavioral keyword,
    career goal, boosted keyword, or job category.  All observed variants
    in scraped data or user profiles resolve to exactly one slug.
    """

    __tablename__ = "taxonomy_terms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="Canonical identifier, e.g. 'machine_learning'",
    )
    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="skill",
        comment="Value type: skill / behavioral / career / boosted / category",
    )
    label: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
        comment="Human-readable display label, e.g. 'Machine Learning'",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )

    # Relationships
    synonyms: Mapped[list["TaxonomySynonym"]] = relationship(
        "TaxonomySynonym", back_populates="term", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<TaxonomyTerm slug={self.slug!r} category={self.category!r}>"


class TaxonomySynonym(Base):
    """An observed variant that maps to a canonical taxonomy term."""

    __tablename__ = "taxonomy_synonyms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    term_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("taxonomy_terms.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    variant: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        comment="Observed raw form, e.g. 'ML', 'Machine Learning', 'ml'",
    )
    source: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Origin: scraper:nofluffjobs, user, SKILLS_REGEX, manual",
    )
    seen_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="How many times observed"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(UTC)
    )

    # Relationships
    term: Mapped["TaxonomyTerm"] = relationship("TaxonomyTerm", back_populates="synonyms")

    def __repr__(self) -> str:
        return f"<TaxonomySynonym variant={self.variant!r} → term_id={self.term_id}>"


class JobTaxonomyTerm(Base):
    """M2M join: which taxonomy terms appear in which job listings."""

    __tablename__ = "job_taxonomy_terms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    term_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("taxonomy_terms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_nice_to_have: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True if this skill is 'nice-to-have' rather than required",
    )

    __table_args__ = (UniqueConstraint("job_id", "term_id", name="uq_job_taxonomy_term"),)
