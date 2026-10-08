"""
Shared test fixtures for the Job Engine.

Provides sample jobs, a mock profile, and a test database setup.
"""

from typing import Any

import pytest
import yaml
from job_engine.database import get_sync_engine, init_db_sync, save_jobs_sync
from job_engine.models import Base

# ─── Sample data ────────────────────────────────────────────────────────────

SAMPLE_JOBS: list[dict[str, Any]] = [
    {
        "external_id": "test_justjoin_001",
        "platform": "justjoin.it",
        "title": "Python Backend Developer",
        "company": "TechCorp",
        "url": "https://justjoin.it/job-offer/test-001",
        "salary_min": 25000,
        "salary_max": 40000,
        "currency": "USD",
        "contract_type": "full_time",
        "location": "Remote",
        "remote": True,
        "skills": ["python", "fastapi", "postgresql", "docker", "redis"],
        "category": "backend",
        "experience_level": "senior",
        "discovered_at": "2026-07-01T10:00:00Z",
    },
    {
        "external_id": "test_nofluff_002",
        "platform": "nofluffjobs.com",
        "title": "Senior Python Engineer",
        "company": "Fintech Inc",
        "url": "https://nofluffjobs.com/pl/job/test-002",
        "salary_min": 30000,
        "salary_max": 50000,
        "currency": "USD",
        "contract_type": "full_time",
        "location": "Remote",
        "remote": True,
        "skills": ["python", "fastapi", "sqlalchemy", "aws", "trading"],
        "category": "backend",
        "experience_level": "senior",
        "discovered_at": "2026-07-01T11:00:00Z",
    },
    {
        "external_id": "test_upwork_003",
        "platform": "upwork.com",
        "title": "Junior Java Developer",
        "company": "OldCorp",
        "url": "https://upwork.com/test-003",
        "salary_min": 5000,
        "salary_max": 8000,
        "currency": "USD",
        "contract_type": "contract",
        "location": "Office",
        "remote": False,
        "skills": ["java", "spring", "hibernate"],
        "category": "backend",
        "experience_level": "junior",
        "discovered_at": "2026-07-01T12:00:00Z",
    },
]


MOCK_PROFILE = {
    "name": "Test User",
    "role": "Backend Python Developer",
    "experience_years": 5,
    "currency": "USD",
    "rate": {"min_monthly": 5000, "max_monthly": 10000},
    "skills": {
        "backend": ["python", "fastapi", "pydantic", "asyncio", "pytest"],
        "databases": ["postgresql", "sqlalchemy", "alembic", "asyncpg", "redis", "mongodb"],
        "devops": ["docker", "aws", "github_actions"],
        "domain": ["fintech", "trading", "backtesting"],
    },
    "critical_categories": ["backend", "databases"],
    "boosted_keywords": ["python", "fastapi", "trading", "fintech", "backtesting"],
    "remote_only": True,
    "preferred_locations": ["remote", "warsaw", "krakow"],
    "excluded_companies": [],
}


# ─── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture
def sample_jobs() -> list[dict[str, Any]]:
    """Return a copy of sample jobs."""
    return [dict(j) for j in SAMPLE_JOBS]


@pytest.fixture
def mock_profile_path(tmp_path) -> str:
    """Write a temporary mock profile YAML."""
    path = tmp_path / "my_profile.yaml"
    with open(path, "w") as f:
        yaml.dump(MOCK_PROFILE, f)
    return str(path)


@pytest.fixture
def mock_profile() -> dict[str, Any]:
    """Return the mock profile as a dict."""
    return dict(MOCK_PROFILE)


BEHAVIORAL_PROFILE = {
    **MOCK_PROFILE,
    "behavioral_keywords": [
        "collaboration",
        "ownership",
        "mentorship",
        "agile",
        "continuous improvement",
    ],
    "career_goals": [
        "tech lead",
        "architecture",
        "distributed systems",
        "machine learning",
        "mentoring",
    ],
}


LEGACY_BEHAVIORAL_PROFILE = {
    **MOCK_PROFILE,
    "behavioral_keywords": {
        "culture": ["collaboration", "ownership", "teamwork"],
        "growth": ["mentorship", "feedback", "continuous improvement"],
    },
    "career_goals": {
        "short_term": ["tech lead", "architecture"],
        "long_term": ["distributed systems", "cto"],
    },
}


CATEGORY_MAPPINGS_PROFILE = {
    **MOCK_PROFILE,
    "category_mappings": {
        "python": ["backend"],
        "data": ["domain"],
        "frontend": [],
        "devops": ["devops"],
    },
    "experience_levels": {
        "intern": 0,
        "junior": 1,
        "mid": 2,
        "senior": 3,
        "staff": 4,
        "principal": 5,
    },
}


@pytest.fixture
def behavioral_profile_path(tmp_path) -> str:
    """Write a temporary profile with behavioral_keywords and career_goals (list format)."""
    path = tmp_path / "behavioral_profile.yaml"
    with open(path, "w") as f:
        yaml.dump(BEHAVIORAL_PROFILE, f)
    return str(path)


@pytest.fixture
def legacy_behavioral_profile_path(tmp_path) -> str:
    """Write a temporary profile with behavioral_keywords and career_goals."""
    path = tmp_path / "legacy_behavioral_profile.yaml"
    with open(path, "w") as f:
        yaml.dump(LEGACY_BEHAVIORAL_PROFILE, f)
    return str(path)


@pytest.fixture
def category_mappings_profile_path(tmp_path) -> str:
    """Write a temporary profile with category_mappings and custom experience_levels."""
    path = tmp_path / "category_mappings_profile.yaml"
    with open(path, "w") as f:
        yaml.dump(CATEGORY_MAPPINGS_PROFILE, f)
    return str(path)


@pytest.fixture
def test_db_engine():
    """Create an in-memory SQLite database for testing."""
    engine = get_sync_engine("sqlite://")
    init_db_sync(engine)
    yield engine
    # Cleanup
    Base.metadata.drop_all(engine)


@pytest.fixture
def test_db_with_jobs(test_db_engine):
    """Create a test DB with sample jobs loaded."""
    save_jobs_sync(SAMPLE_JOBS, engine=test_db_engine)
    return test_db_engine
