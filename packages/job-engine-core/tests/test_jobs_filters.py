"""
Tests for the jobs list filters, sorting, pagination, and scored-cache freshness.

Two shipped defects are covered here:

- Filtering while on page >= 2 returned an empty list, because the requested
  page was neither reset by the client nor clamped by the API against the
  shorter result set.
- Favorite/hidden toggles stayed invisible to the list filters
  (``show_favorites`` / ``hidden_only`` / ``show_hidden``) for up to
  ``SCORED_CACHE_TTL`` seconds, because nothing invalidated the scored cache.
"""

from __future__ import annotations

import pytest
from dashboard import common
from dashboard.jobs_helpers import filter_and_sort_jobs


def _job(**overrides) -> dict:
    """A minimal job dict with the fields the filters/sorts key off."""
    job = {
        "external_id": "job",
        "title": "Backend Engineer",
        "company": "Acme",
        "location": "Remote",
        "platform": "test",
        "match_score": 50,
        "skills": ["python"],
        "favorite": False,
        "hidden": False,
        "application_status": None,
    }
    job.update(overrides)
    return job


class TestFilterAndSortJobs:
    """Unit tests on plain dicts — no DB, no app."""

    def test_show_favorites_keeps_only_favorites(self):
        jobs = [
            _job(external_id="a", favorite=True),
            _job(external_id="b"),
            _job(external_id="c", favorite=True),
        ]

        result = filter_and_sort_jobs(jobs, show_favorites="true")

        assert [j["external_id"] for j in result] == ["a", "c"]

    @pytest.mark.parametrize("sort_order", ["asc", "desc"])
    def test_sort_by_favorite_puts_favorites_first(self, sort_order):
        """Regression: the default ``desc`` order used to reverse the groups."""
        jobs = [
            _job(external_id="a"),
            _job(external_id="b", favorite=True),
            _job(external_id="c", favorite=True),
        ]

        result = filter_and_sort_jobs(jobs, sort_by="favorite", sort_order=sort_order)

        assert [j["favorite"] for j in result] == [True, True, False]

    @pytest.mark.parametrize("sort_order", ["asc", "desc"])
    def test_sort_by_application_puts_applied_first(self, sort_order):
        """Regression: same inversion, and non-``applied`` stages count too."""
        jobs = [
            _job(external_id="a"),
            _job(external_id="b", application_status="interview"),
            _job(external_id="c", application_status="applied"),
        ]

        result = filter_and_sort_jobs(jobs, sort_by="application", sort_order=sort_order)

        assert [j["application_status"] for j in result] == ["interview", "applied", None]

    def test_application_sort_group_matches_show_applied_filter(self):
        """Both places must agree that interview/offer stages count as applied."""
        jobs = [
            _job(external_id="a"),
            _job(external_id="b", application_status="interview"),
            _job(external_id="c", application_status="applied"),
        ]

        filtered = filter_and_sort_jobs(jobs, show_applied="true")
        sorted_jobs = filter_and_sort_jobs(jobs, sort_by="application")
        first_group = [j["external_id"] for j in sorted_jobs if j["application_status"] is not None]

        assert [j["external_id"] for j in filtered] == first_group == ["b", "c"]

    def test_hidden_jobs_and_show_hidden_interplay(self):
        jobs = [_job(external_id="visible"), _job(external_id="hidden", hidden=True)]

        assert [j["external_id"] for j in filter_and_sort_jobs(jobs)] == ["visible"]
        assert [j["external_id"] for j in filter_and_sort_jobs(jobs, show_hidden="true")] == [
            "visible",
            "hidden",
        ]
        assert [j["external_id"] for j in filter_and_sort_jobs(jobs, hidden_only="true")] == [
            "hidden"
        ]


class TestScoredCacheInvalidation:
    """The list filters must see favorite/hidden writes immediately."""

    @pytest.fixture
    def file_db_engine(self, tmp_path):
        """File-backed SQLite engine.

        The toggle route runs its sync helper in a worker thread
        (``asyncio.to_thread``), and an in-memory SQLite URL gives each thread
        its own empty database — so this test needs a real file.
        """
        from job_engine.database import get_sync_engine, init_db_sync, save_jobs_sync
        from job_engine.models import Base

        engine = get_sync_engine(f"sqlite:///{tmp_path / 'jobs.db'}")
        init_db_sync(engine)
        save_jobs_sync(
            [{"external_id": "fav_me", "platform": "test", "title": "Dev"}], engine=engine
        )
        yield engine
        Base.metadata.drop_all(engine)

    def test_invalidate_clears_the_cache(self, monkeypatch):
        monkeypatch.setattr(common, "_scored_cache", {"ts": 0.0, "jobs": [{"external_id": "x"}]})

        common.invalidate_scored_cache()

        assert common._scored_cache is None

    def test_toggle_fav_clears_the_cache(self, file_db_engine, monkeypatch):
        from dashboard.main import app
        from dashboard.routes import jobs
        from fastapi.testclient import TestClient

        monkeypatch.setattr(jobs, "get_engine", lambda: file_db_engine)
        monkeypatch.setattr(common, "_scored_cache", {"ts": 0.0, "jobs": []})

        with TestClient(app) as client:
            resp = client.patch("/api/jobs/fav_me/toggle-fav")

        assert resp.status_code == 200
        assert resp.json()["favorite"] is True
        assert common._scored_cache is None


class TestJobsPaginationClamp:
    """An out-of-range page must not render a misleading empty list."""

    @pytest.fixture
    def client_with_jobs(self, monkeypatch):
        from dashboard.main import app
        from dashboard.routes import jobs
        from fastapi.testclient import TestClient

        monkeypatch.setattr(
            jobs, "get_scored_jobs", lambda: [_job(external_id=f"j{i}") for i in range(3)]
        )
        with TestClient(app) as client:
            yield client

    def test_page_past_the_end_is_clamped(self, client_with_jobs):
        data = client_with_jobs.get("/api/jobs?page=999&per_page=50").json()

        assert data["total"] == 3
        assert data["page"] == 1
        assert len(data["jobs"]) == 3

    def test_partial_last_page_is_kept(self, client_with_jobs):
        data = client_with_jobs.get("/api/jobs?page=2&per_page=2").json()

        assert data["page"] == 2
        assert len(data["jobs"]) == 1
