"""
Tests for the applications API.

Covers GET /api/applications/follow-up, which previously returned 500 with
``TypeError: can't subtract offset-naive and offset-aware datetimes``: SQLite
returns datetime columns as naive values, while the route compares them against
``datetime.now(UTC)``. Also covers the soft-delete guard, which keeps deleted
applications out of the follow-up list.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest
from job_engine.models import Application, Job, as_utc
from sqlalchemy.orm import Session


def _seed_application(
    engine,
    *,
    days_ago: int,
    status: str = "applied",
    last_contact_days_ago: int | None = None,
    deleted: bool = False,
) -> int:
    """Insert one job + application whose activity was ``days_ago`` days back.

    ``last_contact_days_ago`` optionally records a follow-up contact, which
    takes precedence over ``updated_at`` when detecting stale applications.
    ``deleted`` soft-deletes the application (``deleted_at`` set, ``status``
    untouched) like ``DELETE /api/applications/{id}`` does. Returns the new
    application's id.
    """
    with Session(engine) as session:
        job = Job(
            external_id=f"follow_up_{days_ago}_{status}_{last_contact_days_ago}_{deleted}",
            platform="test",
            title="Backend Engineer",
            url="https://example.com/job",
        )
        session.add(job)
        session.flush()
        ts = datetime.now(UTC) - timedelta(days=days_ago)
        application = Application(
            job_id=job.id,
            status=status,
            applied_at=ts,
            updated_at=ts,
            created_at=ts,
            deleted_at=datetime.now(UTC) if deleted else None,
            last_contact_at=(
                datetime.now(UTC) - timedelta(days=last_contact_days_ago)
                if last_contact_days_ago is not None
                else None
            ),
        )
        session.add(application)
        session.commit()
        return application.id


class TestAsUtc:
    """The naive → UTC coercion applied to datetimes read back from SQLite."""

    def test_none_passes_through(self):
        assert as_utc(None) is None

    def test_naive_is_treated_as_utc(self):
        naive = datetime(2026, 1, 2, 3, 4, 5)
        aware = as_utc(naive)
        assert aware is not None
        assert aware.tzinfo is UTC
        assert aware == naive.replace(tzinfo=UTC)

    def test_aware_is_preserved(self):
        aware = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
        assert as_utc(aware) is aware


class TestFollowUpEndpoint:
    """GET /api/applications/follow-up."""

    @pytest.fixture
    def route(self, test_db_engine, monkeypatch):
        """Point the route's DB access at the in-memory test engine."""
        from dashboard.routes import applications

        monkeypatch.setattr(applications, "get_engine", lambda: test_db_engine)
        return applications

    @pytest.mark.asyncio
    async def test_stale_application_reports_days_since_contact(self, route, test_db_engine):
        """A 15-day-old application is returned instead of raising."""
        _seed_application(test_db_engine, days_ago=15)

        data = json.loads((await route.get_follow_up_applications()).body)

        assert len(data) == 1
        assert data[0]["days_since_contact"] == 15
        assert data[0]["job_title"] == "Backend Engineer"

    @pytest.mark.asyncio
    async def test_recent_application_is_excluded(self, route, test_db_engine):
        """Applications contacted within the last 10 days need no follow-up."""
        _seed_application(test_db_engine, days_ago=5)

        data = json.loads((await route.get_follow_up_applications()).body)

        assert data == []

    @pytest.mark.asyncio
    async def test_recent_follow_up_resets_the_clock(self, route, test_db_engine):
        """A recent ``last_contact_at`` wins over an old ``updated_at``."""
        _seed_application(test_db_engine, days_ago=30, last_contact_days_ago=2)

        data = json.loads((await route.get_follow_up_applications()).body)

        assert data == []

    @pytest.mark.asyncio
    async def test_terminal_status_is_excluded(self, route, test_db_engine):
        """Closed applications are never chased for a follow-up."""
        _seed_application(test_db_engine, days_ago=30, status="rejected")

        data = json.loads((await route.get_follow_up_applications()).body)

        assert data == []

    @pytest.mark.asyncio
    async def test_deleted_application_is_excluded(self, route, test_db_engine):
        """A soft-deleted application is hidden even though it is stale."""
        _seed_application(test_db_engine, days_ago=30, deleted=True)

        data = json.loads((await route.get_follow_up_applications()).body)

        assert data == []

    @pytest.mark.asyncio
    async def test_deleted_application_does_not_hide_live_ones(self, route, test_db_engine):
        """Deleting one stale application leaves the other stale ones listed."""
        _seed_application(test_db_engine, days_ago=30, deleted=True)
        live_id = _seed_application(test_db_engine, days_ago=12)

        data = json.loads((await route.get_follow_up_applications()).body)

        assert [row["id"] for row in data] == [live_id]


class TestStatusArchiveAndLogs:
    """PATCH /status, POST /archive and GET /logs."""

    @pytest.fixture
    def route(self, test_db_engine, monkeypatch, tmp_path):
        """Use the in-memory engine and keep archive folders inside tmp_path."""
        from dashboard.routes import applications

        monkeypatch.setattr(applications, "get_engine", lambda: test_db_engine)
        monkeypatch.chdir(tmp_path)
        return applications

    @pytest.mark.asyncio
    async def test_status_change_on_deleted_application_is_404(self, route, test_db_engine):
        from fastapi import HTTPException

        app_id = _seed_application(test_db_engine, days_ago=1, deleted=True)

        with pytest.raises(HTTPException) as exc:
            await route.api_update_application_status(app_id, {"status": "interview"})
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_terminal_status_archives_materials(self, route, test_db_engine, tmp_path):
        app_id = _seed_application(test_db_engine, days_ago=1)

        await route.api_update_application_status(app_id, {"status": "rejected"})

        with Session(test_db_engine) as session:
            app = session.get(Application, app_id)
            assert app is not None
            assert app.archived_materials_path is not None
        meta = json.loads(
            (tmp_path / "data/archives/applications" / str(app_id) / "metadata.json").read_text()
        )
        assert meta["status"] == "rejected"

    @pytest.mark.asyncio
    async def test_archive_requires_explicit_status(self, route, test_db_engine):
        from fastapi import HTTPException

        app_id = _seed_application(test_db_engine, days_ago=1)

        with pytest.raises(HTTPException) as exc:
            await route.archive_application(app_id, {})
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_archive_rejects_invalid_transition(self, route, test_db_engine):
        """interview → accepted skips the offer stage and is not allowed."""
        from fastapi import HTTPException

        app_id = _seed_application(test_db_engine, days_ago=1, status="interview")

        with pytest.raises(HTTPException) as exc:
            await route.archive_application(app_id, {"status": "accepted"})
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_archive_sets_chosen_status(self, route, test_db_engine):
        app_id = _seed_application(test_db_engine, days_ago=1)

        data = json.loads(
            (await route.archive_application(app_id, {"status": "withdrawn"})).body
        )

        assert data["new_status"] == "withdrawn"

    @pytest.mark.asyncio
    async def test_logs_list_transitions_in_order(self, route, test_db_engine):
        app_id = _seed_application(test_db_engine, days_ago=1)
        await route.api_update_application_status(app_id, {"status": "interview"})
        await route.api_update_application_status(app_id, {"status": "offer"})

        logs = json.loads((await route.api_application_logs(app_id)).body)

        assert [(entry["from_status"], entry["to_status"]) for entry in logs] == [
            ("applied", "interview"),
            ("interview", "offer"),
        ]
