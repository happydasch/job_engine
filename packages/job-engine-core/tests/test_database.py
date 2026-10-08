"""
Tests for database helpers (save_jobs_sync, log_scraper_run_sync, etc.).
"""

import json

from job_engine.database import (
    _add_column_if_missing,
    log_scraper_run_sync,
    save_jobs_sync,
)
from job_engine.models import Job, ScraperLog
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session


class TestAddColumnIfMissing:
    """Tests for the _add_column_if_missing migration helper."""

    def _make_table(self):
        engine = create_engine("sqlite://")
        with Session(engine) as session:
            session.execute(text("CREATE TABLE widgets (id INTEGER PRIMARY KEY)"))
            session.commit()
        return engine

    def test_adds_missing_column(self):
        engine = self._make_table()
        _add_column_if_missing(engine, "widgets", "color", "TEXT")
        cols = [c["name"] for c in inspect(engine).get_columns("widgets")]
        assert "color" in cols

    def test_is_idempotent_when_column_exists(self):
        engine = self._make_table()
        _add_column_if_missing(engine, "widgets", "color", "TEXT")
        # Second call must not raise (column already present).
        _add_column_if_missing(engine, "widgets", "color", "TEXT")
        cols = [c["name"] for c in inspect(engine).get_columns("widgets")]
        assert cols.count("color") == 1

    def test_respects_ddl_default(self):
        engine = self._make_table()
        with Session(engine) as session:
            session.execute(text("INSERT INTO widgets (id) VALUES (1)"))
            session.commit()
        _add_column_if_missing(engine, "widgets", "flag", "BOOLEAN NOT NULL DEFAULT 0")
        with Session(engine) as session:
            val = session.execute(text("SELECT flag FROM widgets WHERE id = 1")).scalar_one()
        assert val == 0


class TestSaveJobs:
    """Tests for save_jobs_sync."""

    def test_insert_new_jobs(self, test_db_with_jobs):
        """Should insert new jobs into the database."""
        engine = test_db_with_jobs
        with Session(engine) as session:
            rows = session.execute(select(Job)).scalars().all()
            assert len(rows) >= 3

    def test_upsert_does_not_duplicate(self, test_db_with_jobs, sample_jobs):
        """Saving the same external_id again should update, not insert."""
        engine = test_db_with_jobs
        with Session(engine) as session:
            count_before = len(session.execute(select(Job)).scalars().all())

        # Re-save with same IDs
        new_count = save_jobs_sync(sample_jobs, engine=engine)

        with Session(engine) as session:
            count_after = len(session.execute(select(Job)).scalars().all())

        assert new_count == 0, "Should not insert new rows for existing external_ids"
        assert count_after == count_before, "Total count should not change"

    def test_update_existing_job(self, test_db_with_jobs):
        """Updating an existing job should change its fields."""
        engine = test_db_with_jobs

        # Modify and re-save
        updated_job = {
            "external_id": "test_justjoin_001",
            "platform": "justjoin.it",
            "title": "UPDATED: Python Backend Developer",
            "company": "TechCorp",
            "url": "https://example.com/updated",
            "skills": ["python", "fastapi", "kubernetes"],
        }
        save_jobs_sync([updated_job], engine=engine)

        with Session(engine) as session:
            job = session.execute(
                select(Job).where(Job.external_id == "test_justjoin_001")
            ).scalar_one()
            assert job.title == "UPDATED: Python Backend Developer"
            assert "kubernetes" in json.loads(job.skills)

    def test_empty_external_id_skipped(self, test_db_engine):
        """Jobs without external_id should be skipped."""
        engine = test_db_engine
        new_count = save_jobs_sync([{"title": "Bad Job"}], engine=engine)
        assert new_count == 0


class TestCompanyCreation:
    """Tests for Company entity creation during job save."""

    def test_company_created_on_insert(self, test_db_with_jobs):
        """Inserting jobs should create Company records."""
        engine = test_db_with_jobs
        with Session(engine) as session:
            from job_engine.models import Company

            companies = session.execute(select(Company)).scalars().all()
            names = {c.name for c in companies}
            assert "TechCorp" in names
            assert "Fintech Inc" in names
            assert "OldCorp" in names

    def test_company_has_job_count(self, test_db_with_jobs):
        """Company.jobs should reflect jobs linked to it."""
        engine = test_db_with_jobs
        with Session(engine) as session:
            from job_engine.models import Company

            techcorp = session.execute(
                select(Company).where(Company.name == "TechCorp")
            ).scalar_one()
            assert len(techcorp.jobs) >= 1

    def test_company_reused_on_second_save(self, test_db_with_jobs, sample_jobs):
        """Saving a job with an existing company should reuse the Company record."""
        engine = test_db_with_jobs
        save_jobs_sync(sample_jobs, engine=engine)
        with Session(engine) as session:
            from job_engine.models import Company

            count = len(session.execute(select(Company)).scalars().all())
            assert count == 3  # Only 3 unique companies from sample

    def test_new_company_created_for_new_name(self, test_db_with_jobs):
        """A job from a new company should create a new Company record."""
        engine = test_db_with_jobs
        new_job = {
            "external_id": "test_newco_001",
            "platform": "justjoin.it",
            "title": "New Role",
            "company": "BrandNew Company",
            "skills": ["python"],
        }
        save_jobs_sync([new_job], engine=engine)
        with Session(engine) as session:
            from job_engine.models import Company

            company = session.execute(
                select(Company).where(Company.name == "BrandNew Company")
            ).scalar_one()
            assert company is not None
            assert len(company.jobs) == 1

    def test_company_id_set_on_job(self, test_db_with_jobs):
        """Jobs should have company_id set after save."""
        engine = test_db_with_jobs
        with Session(engine) as session:
            job = session.execute(
                select(Job).where(Job.external_id == "test_justjoin_001")
            ).scalar_one()
            assert job.company_id is not None


class TestScraperLog:
    """Tests for log_scraper_run_sync."""

    def test_log_successful_run(self, test_db_engine):
        """Should create a scraper log entry."""
        engine = test_db_engine
        log_scraper_run_sync(
            scraper="justjoin_it",
            jobs_found=10,
            status="success",
            duration_seconds=12.5,
            engine=engine,
        )

        with Session(engine) as session:
            log = session.execute(select(ScraperLog)).scalar_one()
            assert log.scraper == "justjoin_it"
            assert log.jobs_found == 10
            assert log.status == "success"
            assert log.duration_seconds == 12.5

    def test_log_failed_run(self, test_db_engine):
        """Should create a failed scraper log entry."""
        engine = test_db_engine
        log_scraper_run_sync(
            scraper="upwork",
            jobs_found=0,
            status="failed",
            error_message="Network timeout",
            engine=engine,
        )

        with Session(engine) as session:
            log = session.execute(select(ScraperLog)).scalar_one()
            assert log.status == "failed"
            assert "Network timeout" in log.error_message


class TestApplicationFollowUpColumns:
    """Follow-up tracking columns are created on the applications table."""

    def test_follow_up_columns_present_after_init(self, test_db_engine):
        cols = {c["name"] for c in inspect(test_db_engine).get_columns("applications")}
        assert {"follow_up_count", "follow_up_notes"}.issubset(cols)
