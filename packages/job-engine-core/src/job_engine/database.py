"""
Async database helpers for the Job Engine.

Provides:
- get_session() — async context manager for DB sessions
- init_db() — create all tables
- save_jobs(jobs) — upsert scraped jobs from JSON into the database
"""

import contextlib
import json
import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import CursorResult, Table, create_engine, inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from job_engine.config import config
from job_engine.models import (
    ApplicationLog,
    Base,
    Company,
    Job,
    ScraperLog,
    TaxonomySynonym,
    TaxonomyTerm,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retry helper for transient SQLite lock errors
# ---------------------------------------------------------------------------


def _retry_on_lock(max_retries: int = 3, delay: float = 0.5):
    """Decorator that retries the callable on sqlite3.OperationalError / database is locked.

    Provides defense-in-depth beyond WAL + busy_timeout: if a transaction
    happens to hit a lock even after the busy timeout, we sleep briefly and
    retry up to *max_retries* times.
    """
    import functools
    import time

    import sqlalchemy.exc

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_retries):
                try:
                    return fn(*args, **kwargs)
                except sqlalchemy.exc.OperationalError as e:
                    if "database is locked" in str(e).lower():
                        last_exc = e
                        if attempt < max_retries - 1:
                            logger.warning(
                                "Database locked on %s, retrying (%d/%d)…",
                                fn.__name__,
                                attempt + 1,
                                max_retries,
                            )
                            time.sleep(delay + delay * attempt)  # linear backoff
                        continue
                    raise  # different OperationalError — re-raise immediately
            assert last_exc is not None  # we only exhaust the loop when a lock error occurred
            raise last_exc  # exhausted retries

        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# Engine management
# ---------------------------------------------------------------------------


# Cached sync engine singleton (set by get_sync_engine)
_sync_engine = None


def get_sync_engine(db_url: str | None = None):
    """Create (or return cached) synchronous engine with WAL mode + busy timeout.

    WAL (Write-Ahead Logging) allows concurrent reads while a write is in
    progress.  The busy timeout tells SQLite to retry locked writes instead of
    immediately raising ``database is locked``.

    We use *connect_args* so that *every* new connection (even overflow
    connections from the pool) gets the busy timeout automatically, and a
    PoolEvents listener ensures WAL mode is set on each new connection too.
    """
    global _sync_engine
    if _sync_engine is not None and db_url is None:
        return _sync_engine

    url = db_url or config.database_sync_url
    engine = create_engine(
        url,
        echo=False,
        connect_args={"timeout": 30},  # 30s busy timeout on every conn
        pool_pre_ping=True,  # verify conn before checkout
    )

    # Ensure WAL mode + busy timeout on every new connection via a pool listener
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=wal")
        cursor.execute("PRAGMA busy_timeout=30000")  # 30 seconds
        cursor.close()

    if db_url is None:
        _sync_engine = engine
    return engine


_async_engine = None


def get_or_create_async_engine():
    """Lazy-create and cache the async engine."""
    global _async_engine
    if _async_engine is None:
        _async_engine = create_async_engine(config.database_url, echo=False)
    return _async_engine


_async_session_factory = None


def get_async_session_factory():
    """Return a cached async session factory."""
    global _async_session_factory
    if _async_session_factory is None:
        engine = get_or_create_async_engine()
        _async_session_factory = async_sessionmaker(engine, class_=AsyncSession)
    return _async_session_factory


@contextlib.asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get an async database session. Use as: async with get_session() as session."""
    factory = get_async_session_factory()
    async with factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


def init_db_sync(engine=None):
    """Create all tables and apply schema migrations synchronously.

    Safe to call multiple times: create_all is a no-op for existing tables and
    migrate_existing_db is idempotent (every ALTER is column-existence guarded).
    Running migrations here — not only via `make migrate` — means a model change
    like a new column takes effect on the next app start instead of silently
    drifting from the DB (which surfaces as "no such column").

    Also seeds the taxonomy registry from the built-in SEED_ALIASES map so that
    the taxonomy_terms and taxonomy_synonyms tables are populated on first run
    (idempotent — skips already-seeded slugs).
    """
    if engine is None:
        engine = get_sync_engine()
    Base.metadata.create_all(engine)
    migrate_existing_db(engine)

    # Auto-seed taxonomy from built-in SEED_ALIASES (idempotent)
    try:
        from sqlalchemy.orm import Session

        from job_engine.taxonomy import seed_taxonomy_from_builtins

        with Session(engine) as session:
            created = seed_taxonomy_from_builtins(session)
            if created > 0:
                logger.info("Seeded %d taxonomy terms from built-in aliases", created)
    except Exception:
        logger.warning("Failed to seed taxonomy — continuing without DB taxonomy")

    return engine


def _add_column_if_missing(
    engine, table: str, column: str, ddl: str, message: str | None = None
) -> None:
    """Add *column* (typed by *ddl*) to *table* if it is not already present.

    Re-inspects the live schema on every call so it stays correct after earlier
    migration steps.  Idempotent: a no-op when the column already exists.
    """
    columns = [c["name"] for c in inspect(engine).get_columns(table)]
    if column in columns:
        return
    with Session(engine) as session:
        session.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
        session.commit()
    if message:
        print(message)


def _rebuild_jobs_table_constraint(
    engine, constraint_name: str, old_sqltext: str | None, new_sqltext: str
) -> None:
    """Rebuild the jobs table to add or replace a CHECK constraint.

    SQLite has no ALTER TABLE ADD/DROP CONSTRAINT — changing a CHECK
    constraint means recreating the table: build a copy with the new
    definition, copy the rows across, then swap it in for the original.
    """
    with Session(engine) as session:
        create_sql = session.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='jobs'")
        ).scalar_one()
        index_sqls = [
            row[0]
            for row in session.execute(
                text(
                    "SELECT sql FROM sqlite_master WHERE type='index' "
                    "AND tbl_name='jobs' AND sql IS NOT NULL"
                )
            ).all()
        ]
        if old_sqltext is not None:
            new_create_sql = create_sql.replace(f"CHECK ({old_sqltext})", f"CHECK ({new_sqltext})")
        else:
            new_create_sql = (
                f"{create_sql.rstrip()[:-1]}, CONSTRAINT {constraint_name} CHECK ({new_sqltext}))"
            )
        if new_create_sql == create_sql:
            raise RuntimeError(f"Could not locate {constraint_name} clause in jobs table SQL")

        session.execute(
            text(new_create_sql.replace("CREATE TABLE jobs", "CREATE TABLE jobs_migrating", 1))
        )
        session.execute(text("INSERT INTO jobs_migrating SELECT * FROM jobs"))
        session.execute(text("DROP TABLE jobs"))
        session.execute(text("ALTER TABLE jobs_migrating RENAME TO jobs"))
        for index_sql in index_sqls:
            session.execute(text(index_sql))
        session.commit()


def _create_table_if_missing(model: type[Any], engine) -> None:
    """Create the ORM model's table if it does not exist yet."""
    table = model.__table__
    if not isinstance(table, Table):
        raise TypeError(f"{model.__name__}.__table__ is not a Table: {type(table).__name__}")
    table.create(engine, checkfirst=True)


def migrate_existing_db(engine=None) -> None:
    """Add new tables/columns for schema changes without dropping existing data.

    Handles:
    - Creating the companies table (new)
    - Adding company_id column to jobs table (new FK)
    - Back-filling company_id for existing jobs with company names
    - Dropping the deprecated `company` column from jobs table
    - Renaming `tech_stack` column to `skills` (schema update)
    """
    if engine is None:
        engine = get_sync_engine()

    # Create the companies table (safe if already exists)
    _create_table_if_missing(Company, engine)

    with Session(engine) as session:
        inspector = inspect(engine)
        columns = [c["name"] for c in inspector.get_columns("jobs")]
        if "company_id" not in columns:
            session.execute(
                text(
                    "ALTER TABLE jobs ADD COLUMN company_id "
                    "INTEGER REFERENCES companies(id) ON DELETE SET NULL"
                )
            )
            session.commit()

        # Back-fill company_id for jobs that have a company name but no company_id
        # Use raw SQL since the `company` column is no longer on the ORM model
        inspect_columns = [c["name"] for c in inspector.get_columns("jobs")]
        if "company" in inspect_columns:
            rows = session.execute(
                text(
                    "SELECT id, company FROM jobs "
                    "WHERE company_id IS NULL AND company != '' "
                    "AND company != 'Unknown'"
                )
            ).all()

            for row in rows:
                company = _get_or_create_company(session, row.company)
                session.execute(
                    text("UPDATE jobs SET company_id = :cid WHERE id = :jid"),
                    {"cid": company.id, "jid": row.id},
                )

            if rows:
                session.commit()

    # Create index on company_id if not present
    inspector = inspect(engine)
    indexes = [i["name"] for i in inspector.get_indexes("jobs")]
    if "ix_jobs_company_id" not in indexes:
        with Session(engine) as session:
            session.execute(text("CREATE INDEX ix_jobs_company_id ON jobs(company_id)"))
            session.commit()

    # Sync the contract_type CHECK constraint with the current allowed value
    # list (matching the model + the normalizeFields step in output.js).
    # SQLite has no ALTER TABLE ADD/DROP CONSTRAINT, so this only rebuilds
    # the table when the constraint is actually out of date.
    desired_contract_type_check = (
        "contract_type IN ('b2b', 'permanent', 'uop', 'uz', 'ud', "
        "'full_time', 'part_time', 'contract', 'freelance', 'internship', 'other')"
    )
    inspector = inspect(engine)
    check_constraints = {c["name"]: c["sqltext"] for c in inspector.get_check_constraints("jobs")}
    if check_constraints.get("ck_job_contract_type") != desired_contract_type_check:
        # Backfill existing data: lowercase any mixed-case values in enum-like
        # fields BEFORE the constraint change, so existing rows don't violate it.
        columns = [c["name"] for c in inspector.get_columns("jobs")]
        for field in ("contract_type", "experience_level", "category", "location"):
            if field in columns:
                with Session(engine) as session:
                    result = session.execute(
                        text(
                            f"UPDATE jobs SET {field} = LOWER({field}) "
                            f"WHERE {field} != LOWER({field})"
                        )
                    )
                    if not isinstance(result, CursorResult):
                        raise TypeError(f"Expected CursorResult, got {type(result).__name__}")
                    session.commit()
                    if result.rowcount:
                        print(f"Lowercased {result.rowcount} value(s) in `{field}` column")

        _rebuild_jobs_table_constraint(
            engine,
            "ck_job_contract_type",
            check_constraints.get("ck_job_contract_type"),
            desired_contract_type_check,
        )
        print("Synced ck_job_contract_type constraint (lowercase values)")

    # Add llm_analysis column to jobs table
    _add_column_if_missing(
        engine, "jobs", "llm_analysis", "TEXT", "Added llm_analysis column to jobs table"
    )

    # Add LLM cache columns to jobs table
    for col_name in ("llm_explain_match", "llm_cover_letter", "llm_questions"):
        _add_column_if_missing(
            engine, "jobs", col_name, "TEXT", f"Added {col_name} column to jobs table"
        )

    # Add favorite (bookmark) flag column to jobs table
    _add_column_if_missing(
        engine,
        "jobs",
        "favorite",
        "BOOLEAN NOT NULL DEFAULT 0",
        "Added favorite column to jobs table",
    )

    # Rename `tech_stack` column to `skills` if old name still exists
    inspector = inspect(engine)
    columns = [c["name"] for c in inspector.get_columns("jobs")]
    if "tech_stack" in columns and "skills" not in columns:
        with Session(engine) as session:
            session.execute(text("ALTER TABLE jobs RENAME COLUMN tech_stack TO skills"))
            session.commit()
            print("Renamed `tech_stack` column to `skills` in jobs table")

    # Drop the deprecated `company` column if it still exists
    inspector = inspect(engine)
    columns = [c["name"] for c in inspector.get_columns("jobs")]
    if "company" in columns:
        with Session(engine) as session:
            # SQLite doesn't support DROP COLUMN directly in older versions,
            # but recent SQLite (3.35.0+) does. We use raw SQL.
            session.execute(text("ALTER TABLE jobs DROP COLUMN company"))
            session.commit()
            print("Dropped deprecated `company` column from jobs table")

    # Add outcome_reason and archived_materials_path to applications table
    _add_column_if_missing(
        engine,
        "applications",
        "outcome_reason",
        "VARCHAR(50)",
        "Added outcome_reason column to applications table",
    )
    _add_column_if_missing(
        engine,
        "applications",
        "archived_materials_path",
        "TEXT",
        "Added archived_materials_path column to applications table",
    )

    # Rename scraper_logs `platform` column to `scraper` if old name still exists
    inspector = inspect(engine)
    log_columns = [c["name"] for c in inspector.get_columns("scraper_logs")]
    if "platform" in log_columns and "scraper" not in log_columns:
        with Session(engine) as session:
            session.execute(text("ALTER TABLE scraper_logs RENAME COLUMN platform TO scraper"))
            session.commit()
            print("Renamed `platform` column to `scraper` in scraper_logs table")
    log_indexes = [i["name"] for i in inspector.get_indexes("scraper_logs")]
    if "ix_scraper_logs_platform" in log_indexes:
        with Session(engine) as session:
            session.execute(text("DROP INDEX ix_scraper_logs_platform"))
            if "ix_scraper_logs_scraper" not in log_indexes:
                session.execute(
                    text("CREATE INDEX ix_scraper_logs_scraper ON scraper_logs(scraper)")
                )
            session.commit()
            print("Renamed scraper_logs platform index to ix_scraper_logs_scraper")

    # ── Deduplicate NFJ jobs ─────────────────────────────────────────────
    # NFJ's API returns the same posting once per region (voivodeship),
    # each with a different `id` slug but the same canonical `reference`.
    # Before the scraper was fixed (Jul 2025), the external_id was
    # nfj_<id> which created ~17 DB entries for every multi-city posting.
    # This finds and removes all but the first copy per (title, company).
    inspector = inspect(engine)
    columns = [c["name"] for c in inspector.get_columns("jobs")]
    if "title" in columns:
        with Session(engine) as session:
            dupe_rows = session.execute(
                text(
                    "SELECT id, external_id, title, company_id, platform, location "
                    "FROM jobs "
                    "WHERE platform = 'nofluffjobs.com' "
                    "ORDER BY id"
                )
            ).all()
            if dupe_rows:
                from collections import defaultdict

                groups = defaultdict(list)
                for row in dupe_rows:
                    cid = row.company_id or 0
                    groups[(row.title.lower(), cid)].append(row)

                removed = 0
                for key, rows in groups.items():
                    if len(rows) > 1:
                        # Keep first (lowest id), delete the rest
                        for row in rows[1:]:
                            session.execute(
                                text("DELETE FROM jobs WHERE id = :jid"),
                                {"jid": row.id},
                            )
                            removed += 1
                if removed:
                    session.commit()
                    print(f"Removed {removed} duplicate NFJ jobs (multi-region entries)")

    # ── Taxonomy tables ────────────────────────────────────────────────────
    _create_table_if_missing(TaxonomyTerm, engine)
    _create_table_if_missing(TaxonomySynonym, engine)

    # Add skills_slugs column to jobs table
    _add_column_if_missing(
        engine,
        "jobs",
        "skills_slugs",
        "TEXT NOT NULL DEFAULT '[]'",
        "Added skills_slugs column to jobs table",
    )

    # Create index on taxonomy_synonyms.variant for fast lookup
    inspector = inspect(engine)
    indexes = [i["name"] for i in inspector.get_indexes("taxonomy_synonyms")]
    if "ix_taxonomy_synonyms_variant" not in indexes:
        with Session(engine) as session:
            session.execute(
                text("CREATE INDEX ix_taxonomy_synonyms_variant ON taxonomy_synonyms(variant)")
            )
            session.commit()
            print("Created index on taxonomy_synonyms.variant")

    # ── ApplicationLog table + soft-delete ────────────────────────────────────
    _create_table_if_missing(ApplicationLog, engine)
    _add_column_if_missing(
        engine,
        "applications",
        "deleted_at",
        "DATETIME",
        "Added deleted_at column to applications table (soft-delete)",
    )

    # Add interview_stages and last_contact_at columns to applications table
    _add_column_if_missing(
        engine,
        "applications",
        "interview_stages",
        "TEXT DEFAULT '{}'",
        "Added interview_stages column to applications table",
    )
    _add_column_if_missing(
        engine,
        "applications",
        "last_contact_at",
        "DATETIME",
        "Added last_contact_at column to applications table",
    )

    # Add follow-up tracking columns to applications table
    _add_column_if_missing(
        engine,
        "applications",
        "follow_up_count",
        "INTEGER NOT NULL DEFAULT 0",
        "Added follow_up_count column to applications table (follow-up tracking)",
    )
    _add_column_if_missing(
        engine,
        "applications",
        "follow_up_notes",
        "TEXT",
        "Added follow_up_notes column to applications table (follow-up tracking)",
    )


async def init_db():
    """Create all tables asynchronously."""
    engine = get_or_create_async_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine


# ---------------------------------------------------------------------------
# Save scraped jobs into DB
# ---------------------------------------------------------------------------


def _sanitize(val: Any) -> Any:
    """Strip lone surrogate characters from strings (invalid UTF-8)."""
    if isinstance(val, str):
        return val.encode("utf-8", errors="replace").decode("utf-8")
    return val


def _json_list(val: Any) -> str | None:
    """Serialize a list to a JSON string, or pass through an already-serialized string/None."""
    if val is None:
        return None
    if isinstance(val, list):
        return json.dumps(val)
    return val


def _get_or_create_company(
    session: Session, name: str, cache: dict[str, Company] | None = None
) -> Company:
    """Find a company by name or create it. Returns the Company ORM object.

    An optional `cache` (name -> Company) short-circuits the per-call SELECT.
    Callers doing bulk work should preload it once (see save_jobs_sync) to avoid
    an N+1 query per job.
    """
    name = name.strip()
    if not name:
        name = "Unknown"

    if cache is not None and name in cache:
        return cache[name]

    existing = session.execute(select(Company).where(Company.name == name)).scalar_one_or_none()
    if existing is None:
        existing = Company(name=name)
        session.add(existing)
        session.flush()  # Get the ID immediately

    if cache is not None:
        cache[name] = existing
    return existing


def _parse_dt(val: Any) -> datetime | None:
    """Parse ISO datetime string to datetime, or return None."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    try:
        # Handle ISO format strings like "2026-04-20T09:47:43.983470+00:00"
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        logger.debug("Failed to parse date: %r — returning None", val)
        return None


@_retry_on_lock()
def save_jobs_sync(jobs: list[dict[str, Any]], engine=None) -> int:
    """
    Upsert scraped jobs into the database.
    Returns the number of new jobs inserted.
    """
    if engine is None:
        engine = get_sync_engine()

    # Sanitize all string values to strip surrogates
    for job_data in jobs:
        for k, v in list(job_data.items()):
            job_data[k] = _sanitize(v)

    # Normalize: scrapers write `tech_stack`, the scorer and DB read `skills`
    for job_data in jobs:
        if not job_data.get("skills") and job_data.get("tech_stack"):
            job_data["skills"] = job_data["tech_stack"]

    # Normalize contract_type: scrapers use various values (B2B, PERMANENT, UoP, UZ, UD, etc.)
    # that are valid in the updated model; map empties to a safe default.
    valid_contract_types = {
        "b2b",
        "permanent",
        "uop",
        "uz",
        "ud",
        "full_time",
        "part_time",
        "contract",
        "freelance",
        "internship",
        "other",
    }
    for job_data in jobs:
        ct_raw = str(job_data.get("contract_type", "")).strip()
        ct_lower = ct_raw.lower()
        if not ct_lower or ct_lower not in valid_contract_types:
            job_data["contract_type"] = "other"
        else:
            job_data["contract_type"] = ct_lower  # match CHECK constraint

    # Compute match scores for all jobs before upserting
    try:
        from job_engine.skill_scorer import JobMatcher

        matcher = JobMatcher()
        for job_data in jobs:
            details = matcher.score_detail(job_data)
            job_data["match_score"] = details["total_score"]
    except Exception:
        logger.warning("Failed to compute match scores during save — continuing without scores")

    # Resolve skills through taxonomy to populate skills_slugs
    try:
        from job_engine.taxonomy import TaxonomyResolver

        _tax_resolver = TaxonomyResolver()

        def _resolve_skills_for_job(job_data: dict) -> list[str]:
            raw_skills = job_data.get("skills", [])
            if isinstance(raw_skills, str):
                try:
                    raw_skills = json.loads(raw_skills)
                except (json.JSONDecodeError, TypeError):
                    raw_skills = []
            if not isinstance(raw_skills, list):
                raw_skills = []
            return _tax_resolver.resolve_many(raw_skills, "skill")
    except Exception:
        logger.warning(
            "Failed to initialize TaxonomyResolver — skills will not be resolved", exc_info=True
        )
        _tax_resolver = None

        def _resolve_skills_for_job(job_data: dict) -> list[str]:
            return []

    for job_data in jobs:
        if _tax_resolver is not None:
            job_data["skills_slugs"] = _resolve_skills_for_job(job_data)

    new_count = 0
    with Session(engine) as session:
        # Preload all existing companies once (name -> Company) so the per-job
        # company resolution below is a dict lookup, not a SELECT each iteration.
        company_cache: dict[str, Company] = {
            c.name: c for c in session.execute(select(Company)).scalars()
        }

        for job_data in jobs:
            external_id = job_data.get("external_id", "")
            if not external_id:
                continue

            # Check if exists
            existing = session.execute(
                select(Job).where(Job.external_id == external_id)
            ).scalar_one_or_none()

            if existing:
                # Update fields that may have changed
                for field in (
                    "title",
                    "salary_min",
                    "salary_max",
                    "currency",
                    "location",
                    "remote",
                    "skills",
                    "skills_slugs",
                    "experience_level",
                    "category",
                    "requirements",
                    "description",
                    "match_score",
                    "secondary_salary_min",
                    "secondary_salary_max",
                    "secondary_currency",
                    "secondary_contract_type",
                    "benefits",
                    "languages",
                    "nice_to_have_skills",
                    "hybrid",
                    "contract_time",
                    "working_time",
                    "division",
                    "valid_from",
                    "valid_to",
                    "published_at",
                    "expired_at",
                    "last_published_at",
                    "latitude",
                    "longitude",
                    "street",
                ):
                    if field in job_data:
                        val = job_data[field]
                        # Map requirements to description
                        db_field = "description" if field == "requirements" else field
                        # Parse date fields
                        if db_field in (
                            "valid_from",
                            "valid_to",
                            "published_at",
                            "expired_at",
                            "last_published_at",
                        ):
                            val = _parse_dt(val)
                        if db_field in (
                            "skills",
                            "skills_slugs",
                            "benefits",
                            "languages",
                            "nice_to_have_skills",
                        ) and isinstance(val, list):
                            val = json.dumps(val)
                        setattr(existing, db_field, val)

                # Resolve company reference
                company_name = job_data.get("company", "").strip()
                if company_name:
                    company = _get_or_create_company(session, company_name, company_cache)
                    existing.company_id = company.id

                existing.updated_at = datetime.now(UTC)
            else:
                # Resolve company reference before creating job
                company_name = job_data.get("company", "Unknown").strip()
                company_id = None
                if company_name and company_name != "Unknown":
                    company = _get_or_create_company(session, company_name, company_cache)
                    company_id = company.id

                job = Job(
                    external_id=external_id,
                    platform=job_data.get("platform", "unknown"),
                    title=job_data.get("title", "Unknown"),
                    company_id=company_id,
                    url=job_data.get("url", ""),
                    description=job_data.get("description") or job_data.get("requirements"),
                    salary_min=job_data.get("salary_min"),
                    salary_max=job_data.get("salary_max"),
                    currency=job_data.get("currency", "USD"),
                    contract_type=job_data.get("contract_type", "full_time"),
                    location=job_data.get("location", "Remote"),
                    remote=job_data.get("remote", False),
                    city=job_data.get("city"),
                    skills=json.dumps(job_data.get("skills", [])),
                    skills_slugs=json.dumps(job_data.get("skills_slugs", [])),
                    category=job_data.get("category", ""),
                    experience_level=job_data.get("experience_level", ""),
                    match_score=job_data.get("match_score"),
                    # New enriched fields
                    secondary_salary_min=job_data.get("secondary_salary_min"),
                    secondary_salary_max=job_data.get("secondary_salary_max"),
                    secondary_currency=job_data.get("secondary_currency"),
                    secondary_contract_type=job_data.get("secondary_contract_type"),
                    benefits=_json_list(job_data.get("benefits")),
                    languages=_json_list(job_data.get("languages")),
                    nice_to_have_skills=_json_list(job_data.get("nice_to_have_skills")),
                    hybrid=job_data.get("hybrid", False),
                    contract_time=job_data.get("contract_time", "full_time"),
                    working_time=job_data.get("working_time", "full_time"),
                    division=job_data.get("division"),
                    valid_from=_parse_dt(job_data.get("valid_from")),
                    valid_to=_parse_dt(job_data.get("valid_to")),
                    published_at=_parse_dt(job_data.get("published_at")),
                    expired_at=_parse_dt(job_data.get("expired_at")),
                    last_published_at=_parse_dt(job_data.get("last_published_at")),
                    latitude=job_data.get("latitude"),
                    longitude=job_data.get("longitude"),
                    street=job_data.get("street"),
                )
                session.add(job)
                new_count += 1

        session.commit()

    return new_count


# ---------------------------------------------------------------------------
# ScraperLog helpers
# ---------------------------------------------------------------------------


@_retry_on_lock()
def log_scraper_run_sync(
    scraper: str,
    jobs_found: int,
    status: str = "success",
    error_message: str | None = None,
    duration_seconds: float | None = None,
    details: dict[str, Any] | None = None,
    engine=None,
):
    """Record a scraper run in the database."""
    if engine is None:
        engine = get_sync_engine()

    with Session(engine) as session:
        log_entry = ScraperLog(
            scraper=scraper,
            status=status,
            jobs_found=jobs_found,
            error_message=error_message,
            duration_seconds=duration_seconds,
            details=json.dumps(details) if details else None,
        )
        session.add(log_entry)
        session.commit()
