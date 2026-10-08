"""
Tests for the scrape API endpoints.

Tests POST /api/scrape, GET /api/scrape/status, GET /api/scrape/status/{run_id},
and GET /api/scrape/history using the TestClient.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from job_engine.scraper_runner import ScraperRun, ScraperRunManager
from job_engine.task_manager import Task, get_task_manager


@pytest.fixture
def manager():
    """Return a fresh ScraperRunManager for each test."""
    return ScraperRunManager()


@pytest.fixture
def client(monkeypatch):
    """Create a TestClient that uses the real app but with a mocked manager."""
    from dashboard.main import app

    with TestClient(app) as c:
        yield c


class TestApiScrapeStart:
    """POST /api/scrape"""

    def test_start_returns_task_id(self, client, manager):
        """Starting a scraper should return a task_id and 200."""
        task_id = "abc123"
        # Pre-populate the TaskManager with the task the endpoint will look up
        tm = get_task_manager()
        task = Task(task_id, "scraper_run", "test")
        run = ScraperRun(task_id)
        task.metadata["scraper_run"] = run
        tm._tasks[task_id] = task

        with patch("dashboard.routes.scrapers.get_scraper_manager", return_value=manager):
            with patch.object(manager, "start_run", new=AsyncMock(return_value=task_id)):
                resp = client.post("/api/scrape")
                assert resp.status_code == 200
                data = resp.json()
                assert data["task_id"] == task_id
                assert data["status"] == "running"

    def test_start_conflict_returns_409(self, client, manager):
        """If a run is already active, should return 409."""
        # Register an active task in TaskManager so the route's error handler finds it
        tm = get_task_manager()
        task = Task("active123", "scraper_run", "test")
        run = ScraperRun("active123")
        run.status = "running"
        task.metadata["scraper_run"] = run
        tm._tasks["active123"] = task

        with patch("dashboard.routes.scrapers.get_scraper_manager", return_value=manager):
            with patch.object(
                manager, "start_run", new=AsyncMock(side_effect=RuntimeError("already in progress"))
            ):
                resp = client.post("/api/scrape")
                assert resp.status_code == 409
                data = resp.json()
                assert "error" in data


class TestApiScrapeStatus:
    """GET /api/scrape/status"""

    def test_status_idle_when_no_runs(self, client, manager):
        """With no runs, status should be 'idle'."""
        with patch("dashboard.routes.scrapers.get_scraper_manager", return_value=manager):
            resp = client.get("/api/scrape/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "idle"
            assert data["last_run"] is None

    def test_status_active_when_running(self, client, manager):
        """With an active run, status should reflect running state."""
        tm = get_task_manager()
        run = ScraperRun("test123")
        run.scrapers_total = 5
        task = Task("test123", "scraper_run", "test")
        task.metadata["scraper_run"] = run
        tm._tasks["test123"] = task

        with patch("dashboard.routes.scrapers.get_scraper_manager", return_value=manager):
            resp = client.get("/api/scrape/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "running"
            # to_dict() includes both run_id and task_id
            assert data["run_id"] == "test123"

    def test_status_by_run_id(self, client, manager):
        """GET /api/scrape/status/{run_id} should return that run's status."""
        tm = get_task_manager()
        run = ScraperRun("specific_id")
        task = Task("specific_id", "scraper_run", "test")
        task.metadata["scraper_run"] = run
        tm._tasks["specific_id"] = task

        with patch("dashboard.routes.scrapers.get_scraper_manager", return_value=manager):
            resp = client.get("/api/scrape/status/specific_id")
            assert resp.status_code == 200
            data = resp.json()
            assert data["run_id"] == "specific_id"
            assert data["status"] == "running"

    def test_status_by_run_id_not_found(self, client, manager):
        """Non-existent run_id should return 404."""
        with patch("dashboard.routes.scrapers.get_scraper_manager", return_value=manager):
            resp = client.get("/api/scrape/status/nonexistent")
            assert resp.status_code == 404


class TestApiScrapeHistory:
    """GET /api/scrape/history"""

    def test_history_empty(self, client, manager):
        """With no runs, history should be empty."""
        with patch("dashboard.routes.scrapers.get_scraper_manager", return_value=manager):
            with patch.object(manager, "get_run_history", return_value=[]):
                resp = client.get("/api/scrape/history")
                assert resp.status_code == 200
                data = resp.json()
                assert isinstance(data, list)
                assert len(data) == 0


class TestApiScrapeCancel:
    """POST /api/scrape/cancel/{task_id}"""

    def test_cancel_active_run(self, client, manager):
        """Cancel an active run should return success."""
        run = ScraperRun("active123")
        run.status = "running"

        with patch("dashboard.routes.scrapers.get_scraper_manager", return_value=manager):
            with patch.object(manager, "cancel_run", new=AsyncMock(return_value=run.to_dict())):
                resp = client.post("/api/scrape/cancel/active123")
                assert resp.status_code == 200
                data = resp.json()
                assert data["success"] is True
                assert "run" in data

    def test_cancel_nonexistent_run(self, client, manager):
        """Cancel a non-existent run should return 400."""
        with patch("dashboard.routes.scrapers.get_scraper_manager", return_value=manager):
            with patch.object(
                manager,
                "cancel_run",
                new=AsyncMock(side_effect=ValueError("Run nonexistent not found")),
            ):
                resp = client.post("/api/scrape/cancel/nonexistent")
                assert resp.status_code == 400
                data = resp.json()
                assert data["success"] is False
                assert "error" in data


class TestScrapersEndpoint:
    def test_list_scrapers(self, client, manager):
        """Should return a list of scrapers with enabled state."""
        with patch("dashboard.routes.scrapers.get_scraper_manager", return_value=manager):
            resp = client.get("/api/scrape/scrapers")
            assert resp.status_code == 200
            data = resp.json()
            assert "scrapers" in data
            assert isinstance(data["scrapers"], list)

    def test_toggle_scraper_unknown(self, client, manager):
        """Toggling an unknown scraper should return 404."""
        with patch("dashboard.routes.scrapers.get_scraper_manager", return_value=manager):
            resp = client.put("/api/scrape/scrapers/nonexistent_scraper", json={"enabled": True})
            assert resp.status_code == 404


class TestScheduleEndpoint:
    """Tests for GET/PUT /api/scrape/schedule."""

    def test_get_schedule(self, client, manager):
        """Should return the scheduler config."""
        with patch("dashboard.routes.scrapers.get_scraper_manager", return_value=manager):
            resp = client.get("/api/scrape/schedule")
            assert resp.status_code == 200
            data = resp.json()
            # Scheduler config should have enabled and interval_minutes
            assert "enabled" in data or "interval_minutes" in data

    def test_set_schedule(self, client, manager):
        """Should update scheduler config."""
        with patch("dashboard.routes.scrapers.get_scraper_manager", return_value=manager):
            with patch.object(
                manager,
                "set_scheduler_config",
                new=AsyncMock(return_value={"enabled": True, "interval_minutes": 60}),
            ):
                resp = client.put(
                    "/api/scrape/schedule", json={"enabled": True, "interval_minutes": 60}
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["enabled"] is True

    def test_set_schedule_invalid(self, client, manager):
        """Setting with invalid data should still return 200 with sanitized config."""
        with patch("dashboard.routes.scrapers.get_scraper_manager", return_value=manager):
            with patch.object(
                manager,
                "set_scheduler_config",
                new=AsyncMock(return_value={"enabled": False, "interval_minutes": 360}),
            ):
                resp = client.put("/api/scrape/schedule", json={"invalid": True})
                assert resp.status_code == 200
