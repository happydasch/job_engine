"""
Tests for the SQLAlchemy models and database helpers.
"""

import json

from job_engine.models import JOB_STATUSES, Application, Company, Job, ScraperLog
from sqlalchemy import select
from sqlalchemy.orm import Session


class TestJobModel:
    """Tests for the Job model."""

    def test_create_job(self, test_db_engine):
        with Session(test_db_engine) as session:
            job = Job(
                external_id="test_001",
                platform="justjoin.it",
                title="Python Developer",
                url="https://example.com/job",
                salary_min=20000,
                salary_max=35000,
                currency="USD",
                contract_type="full_time",
                location="Remote",
                remote=True,
                skills='["python", "fastapi"]',
                category="python",
                experience_level="senior",
            )
            session.add(job)
            session.commit()
            assert job.id is not None
            assert job.status == "new"

    def test_job_repr(self, test_db_with_jobs):
        with Session(test_db_with_jobs) as session:
            job = session.execute(select(Job).limit(1)).scalar_one()
            r = repr(job)
            assert "Job" in r
            assert "justjoin.it" in r or "nofluffjobs.com" in r or "upwork.com" in r

    def test_skills_list_property(self, test_db_with_jobs):
        with Session(test_db_with_jobs) as session:
            job = session.execute(select(Job).limit(1)).scalar_one()
            skills = job.skills_list
            assert isinstance(skills, list)
            assert len(skills) > 0

    def test_skills_list_setter(self, test_db_engine):
        with Session(test_db_engine) as session:
            job = Job(
                external_id="test_002",
                platform="justjoin.it",
                title="Test",
                url="https://example.com",
                skills="[]",
            )
            job.skills_list = ["python", "docker"]
            session.add(job)
            session.commit()
            assert json.loads(job.skills) == ["python", "docker"]

    def test_salary_range(self, test_db_with_jobs):
        with Session(test_db_with_jobs) as session:
            job = session.execute(select(Job).limit(1)).scalar_one()
            r = job.salary_range
            assert "-" in r or "from" in r or "up to" in r or "N/A" in r

    def test_is_remote(self, test_db_with_jobs):
        with Session(test_db_with_jobs) as session:
            jobs = session.execute(select(Job)).scalars().all()
            assert any(j.is_remote for j in jobs)

    def test_job_statuses(self):
        assert "new" in JOB_STATUSES
        assert "matched" in JOB_STATUSES
        assert "applied" in JOB_STATUSES


class TestApplicationModel:
    """Tests for the Application model."""

    def test_create_application(self, test_db_with_jobs):
        with Session(test_db_with_jobs) as session:
            job = session.execute(select(Job).limit(1)).scalar_one()
            app = Application(
                job_id=job.id,
                status="applied",
                cover_letter="I am interested in this position.",
            )
            session.add(app)
            session.commit()
            assert app.id is not None
            assert app.status == "applied"

    def test_application_relationship(self, test_db_with_jobs):
        with Session(test_db_with_jobs) as session:
            job = session.execute(select(Job).limit(1)).scalar_one()
            app = Application(job_id=job.id, status="applied")
            session.add(app)
            session.commit()
            # Refresh and check relationship
            session.refresh(job)
            assert len(job.applications) >= 1

    def test_application_repr(self, test_db_with_jobs):
        with Session(test_db_with_jobs) as session:
            job = session.execute(select(Job).limit(1)).scalar_one()
            app = Application(job_id=job.id, status="interview")
            session.add(app)
            session.commit()
            r = repr(app)
            assert "Application" in r
            assert "interview" in r


class TestCompanyModel:
    """Tests for the Company model."""

    def test_create_company(self, test_db_engine):
        with Session(test_db_engine) as session:
            company = Company(
                name="TestCorp",
                url="https://testcorp.com",
                industry="Technology",
                size_range="50-200",
                headquarters="Warsaw",
                founded_year=2020,
            )
            session.add(company)
            session.commit()
            assert company.id is not None
            assert company.name == "TestCorp"

    def test_company_repr(self, test_db_engine):
        with Session(test_db_engine) as session:
            c = Company(name="Acme Inc")
            session.add(c)
            session.commit()
            r = repr(c)
            assert "Company" in r
            assert "Acme Inc" in r

    def test_company_unique_name(self, test_db_engine):
        with Session(test_db_engine) as session:
            c1 = Company(name="UniqueCo")
            session.add(c1)
            session.commit()
            c2 = Company(name="UniqueCo")
            session.add(c2)
            import pytest

            with pytest.raises(Exception):
                session.commit()

    def test_company_job_relationship(self, test_db_engine):
        with Session(test_db_engine) as session:
            company = Company(name="RelCo")
            session.add(company)
            session.flush()
            job = Job(
                external_id="test_rel_001",
                platform="justjoin.it",
                title="Rel Job",
                company_id=company.id,
                url="https://example.com",
                skills="[]",
            )
            session.add(job)
            session.commit()
            session.refresh(company)
            assert len(company.jobs) == 1
            assert company.jobs[0].title == "Rel Job"


class TestScraperLogModel:
    """Tests for the ScraperLog model."""

    def test_create_log(self, test_db_engine):
        with Session(test_db_engine) as session:
            log = ScraperLog(
                scraper="justjoin_it",
                status="success",
                jobs_found=15,
                duration_seconds=12.5,
            )
            session.add(log)
            session.commit()
            assert log.id is not None

    def test_log_repr(self, test_db_engine):
        with Session(test_db_engine) as session:
            log = ScraperLog(
                scraper="nofluffjobs",
                status="failed",
                jobs_found=0,
                error_message="Playwright not available",
            )
            session.add(log)
            session.commit()
            r = repr(log)
            assert "ScraperLog" in r
            assert "failed" in r
