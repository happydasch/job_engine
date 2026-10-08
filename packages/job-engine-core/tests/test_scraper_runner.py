"""
Tests for the dashboard-controlled scraper runner (ScraperRunManager).

Tests state machine, run lifecycle, conflict detection, and error handling
using mocked subprocesses.
"""

import asyncio
import contextlib
import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from job_engine.scraper_runner import (
    ScraperRun,
    ScraperRunManager,
    _parse_stdout_line,
    _seed_results,
    get_scraper_manager,
)
from job_engine.task_manager import Task, get_task_manager

# Controlled scraper IDs for testing (independent of real Node.js dump)
_TEST_SCRAPER_IDS = ["scraper_a", "scraper_b", "scraper_c"]


class TestScraperRunModel:
    """Tests for the ScraperRun in-memory state model."""

    def test_init(self):
        run_id = uuid.uuid4().hex[:12]
        run = ScraperRun(run_id)
        assert run.run_id == run_id
        assert run.status == "running"
        assert run.started_at is not None
        assert run.completed_at is None
        assert run.scrapers_total == 0
        assert run.scrapers_completed == 0
        assert run.jobs_found_total == 0
        assert run.jobs_new_seeded == 0
        assert run.scraper_statuses == {}
        assert run.error_message is None

    def test_elapsed_seconds_active(self):
        run = ScraperRun("test123")
        elapsed = run.elapsed_seconds
        assert elapsed >= 0

    def test_elapsed_seconds_completed(self):
        run = ScraperRun("test123")
        run.completed_at = run.started_at
        assert run.elapsed_seconds == 0.0

    def test_to_dict_contains_all_fields(self):
        run = ScraperRun("test456")
        run.scrapers_total = 5
        run.scrapers_completed = 2
        run.jobs_found_total = 42
        d = run.to_dict()
        assert d["run_id"] == "test456"
        assert d["status"] == "running"
        assert "started_at" in d
        assert d["scrapers_total"] == 5
        assert d["scrapers_completed"] == 2
        assert d["jobs_found_total"] == 42
        assert "elapsed_seconds" in d
        assert "scraper_statuses" in d


class TestScraperRunManager:
    """Tests for the ScraperRunManager."""

    @pytest.fixture(autouse=True)
    def reset_manager(self):
        """Reset the singleton for each test."""
        # The module-level _manager is problematic for testing;
        # we create a fresh instance for each test.
        from job_engine import task_manager as tm_mod

        tm_mod._manager = None
        self.manager = ScraperRunManager()

    def _mock_start_run_deps(self, runner_mock=None):
        """Patch the infrastructure that start_run depends on but tests shouldn't exercise."""
        if runner_mock is None:

            async def _mock_runner(task, *args, **kwargs):
                run = ScraperRun(task.task_id)
                run.scrapers_total = len(_TEST_SCRAPER_IDS)
                run.scraper_statuses = {pid: "pending" for pid in _TEST_SCRAPER_IDS}
                task.metadata["scraper_run"] = run

            runner_mock = _mock_runner
        stack = contextlib.ExitStack()
        stack.enter_context(patch("job_engine.scraper_runner._run_scraper_task", new=runner_mock))
        stack.enter_context(
            patch.object(
                self.manager, "_write_temp_config", return_value="/tmp/_test_dashboard_config.yaml"
            )
        )
        stack.enter_context(patch.object(self.manager, "_cleanup_temp_config"))
        return stack

    def _mock_scraper_ids(self, ids=None):
        """Mock get_scraper_config to return controlled test data."""
        if ids is None:
            ids = _TEST_SCRAPER_IDS
        mock_cfg = MagicMock()
        mock_cfg.get_active_ids.return_value = ids
        mock_cfg.list_scrapers.return_value = [
            {"id": pid, "enabled": True, "label": pid} for pid in ids
        ]
        return patch("job_engine.scraper_runner.get_scraper_config", return_value=mock_cfg)

    @pytest.mark.asyncio
    async def test_start_run_creates_run(self):
        """Starting a run should create a new run and initialize scraper statuses."""
        with self._mock_scraper_ids():
            with self._mock_start_run_deps():
                run_id = await self.manager.start_run()
                # Yield control inside the patch context so the background mock runner executes
                await asyncio.sleep(0)

        assert run_id is not None
        run = self.manager.get_run(run_id)
        assert run is not None
        assert run.status == "running"
        assert run.scrapers_total == len(_TEST_SCRAPER_IDS)
        assert len(run.scraper_statuses) == len(_TEST_SCRAPER_IDS)
        # All should be pending
        for pid in _TEST_SCRAPER_IDS:
            assert run.scraper_statuses.get(pid) == "pending"

    @pytest.mark.asyncio
    async def test_start_run_conflict(self):
        """Starting a second run while one is active should raise RuntimeError."""
        with self._mock_scraper_ids():
            with self._mock_start_run_deps():
                await self.manager.start_run()

            with pytest.raises(RuntimeError, match="already in progress"):
                await self.manager.start_run()

    @pytest.mark.asyncio
    async def test_get_active_run(self):
        """get_active_run should return the currently running run."""
        # Register a running task with a ScraperRun directly via TaskManager
        tm = get_task_manager()
        run = ScraperRun("test_active")
        task = Task("test_active", "scraper_run", "test")
        task.metadata["scraper_run"] = run
        tm._tasks["test_active"] = task

        active = self.manager.get_active_run()
        assert active is not None
        assert active.status == "running"

    def test_get_active_run_idle(self):
        """get_active_run should return None when no run is active."""
        active = self.manager.get_active_run()
        assert active is None

    def test_get_last_run_empty(self):
        """get_last_run should return None when no runs exist."""
        last = self.manager.get_last_run()
        assert last is None

    @pytest.mark.asyncio
    async def test_get_last_run_with_runs(self):
        """get_last_run should return the most recent run."""
        with self._mock_scraper_ids():
            with self._mock_start_run_deps():
                run1_id = await self.manager.start_run()
                await asyncio.sleep(0)
            # Manually complete the first run
            run1 = self.manager.get_run(run1_id)
            run1.status = "completed"

            with self._mock_start_run_deps():
                run2_id = await self.manager.start_run()
                await asyncio.sleep(0)
            run2 = self.manager.get_run(run2_id)
            run2.status = "completed"

        last = self.manager.get_last_run()
        assert last is not None
        assert last.run_id == run2_id

    @pytest.mark.asyncio
    async def test_spawn_failure_sets_error(self):
        """If the runner raises, the task should be marked as failed."""

        async def mock_runner_raises(task, *args, **kwargs):
            raise FileNotFoundError("Script not found")

        with self._mock_scraper_ids():
            with self._mock_start_run_deps(runner_mock=mock_runner_raises):
                # start_run no longer raises — the runner runs asynchronously
                run_id = await self.manager.start_run()
                # Yield control inside the patch context so the background task runs and fails
                await asyncio.sleep(0)

        # After failure, there should be no active runs
        assert self.manager.get_active_run() is None
        # The task should exist but have no scraper_run in metadata
        assert self.manager.get_run(run_id) is None

    @pytest.mark.asyncio
    async def test_cancel_run_active(self):
        """Cancel an active run should kill the process and mark as failed."""
        mock_process = AsyncMock()
        mock_process.wait = AsyncMock(return_value=0)
        mock_process.kill = MagicMock()

        # Register a running task directly via TaskManager
        tm = get_task_manager()
        run = ScraperRun("cancel_test")
        run.scrapers_total = 1
        run.scraper_statuses = {"test": "running"}
        run._process = mock_process
        task = Task("cancel_test", "scraper_run", "test")
        task.metadata["scraper_run"] = run
        tm._tasks["cancel_test"] = task

        result = await self.manager.cancel_run("cancel_test")

        assert result["status"] == "failed"
        assert result["error_message"] == "Run cancelled by user"
        assert "completed_at" in result
        assert result["completed_at"] is not None
        mock_process.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_run_nonexistent(self):
        """Cancel a non-existent run should raise ValueError."""
        with pytest.raises(ValueError, match="not found"):
            await self.manager.cancel_run("nonexistent")

    @pytest.mark.asyncio
    async def test_cancel_run_not_running(self):
        """Cancel a completed run should raise ValueError."""
        run = ScraperRun("test123")
        run.status = "completed"
        # Register a completed task via TaskManager
        tm = get_task_manager()
        task = Task("test123", "scraper_run", "test")
        task.metadata["scraper_run"] = run
        task.status = "completed"
        tm._tasks["test123"] = task

        with pytest.raises(ValueError, match="not running"):
            await self.manager.cancel_run("test123")

    def test_get_run_nonexistent(self):
        """get_run should return None for a non-existent run_id."""
        run = self.manager.get_run("nonexistent")
        assert run is None

    @patch("job_engine.scraper_runner.get_scraper_ids")
    def test_parse_stdout_line_scraper_completed(self, mock_ids):
        """Parse a scraper_done event and update scraper status + counts."""
        mock_ids.return_value = _TEST_SCRAPER_IDS + ["justjoin_it"]
        run = ScraperRun("test")
        run.scrapers_total = len(_TEST_SCRAPER_IDS)
        run.scraper_statuses = {pid: "pending" for pid in _TEST_SCRAPER_IDS}

        _parse_stdout_line(
            run,
            (
                '##SCRAPER_EVENT## {"type":"scraper_done","id":"justjoin_it",'
                '"jobs":15,"duration":12.3,"error":null,"skipped":false}'
            ),
        )
        assert run.scraper_statuses["justjoin_it"] == "completed"
        assert run.jobs_found_total >= 15
        assert run.scraper_job_counts["justjoin_it"] == 15

    @patch("job_engine.scraper_runner.get_scraper_ids")
    def test_parse_stdout_line_done_counted_once(self, mock_ids):
        """A duplicate scraper_done event must not double-count the scraper."""
        mock_ids.return_value = _TEST_SCRAPER_IDS + ["justjoin_it"]
        run = ScraperRun("test")
        run.scraper_statuses = {pid: "pending" for pid in _TEST_SCRAPER_IDS}

        event = (
            '##SCRAPER_EVENT## {"type":"scraper_done","id":"justjoin_it",'
            '"jobs":15,"duration":12.3,"error":null,"skipped":false}'
        )
        _parse_stdout_line(run, event)
        _parse_stdout_line(run, event)
        assert run.scrapers_completed == 1
        assert run.jobs_found_total == 15

    @patch("job_engine.scraper_runner.get_scraper_ids")
    def test_parse_stdout_line_skipped(self, mock_ids):
        """A skipped scraper is marked skipped and contributes no stale jobs."""
        mock_ids.return_value = _TEST_SCRAPER_IDS + ["remoteok"]
        run = ScraperRun("test")
        run.scraper_statuses = {pid: "pending" for pid in _TEST_SCRAPER_IDS}

        _parse_stdout_line(
            run,
            (
                '##SCRAPER_EVENT## {"type":"scraper_done","id":"remoteok",'
                '"jobs":0,"duration":0,"error":null,"skipped":true}'
            ),
        )
        assert run.scraper_statuses["remoteok"] == "skipped"
        assert run.jobs_found_total == 0

    @patch("job_engine.scraper_runner.get_scraper_ids")
    def test_parse_stdout_line_scraper_running(self, mock_ids):
        """Parse a scraper_start event and set scraper to running."""
        mock_ids.return_value = _TEST_SCRAPER_IDS + ["nofluffjobs"]
        run = ScraperRun("test")
        run.scraper_statuses = {pid: "pending" for pid in _TEST_SCRAPER_IDS}

        _parse_stdout_line(
            run,
            '##SCRAPER_EVENT## {"type":"scraper_start","id":"nofluffjobs"}',
        )
        assert run.scraper_statuses["nofluffjobs"] == "running"

    @patch("job_engine.scraper_runner.get_scraper_ids")
    def test_parse_stdout_line_error(self, mock_ids):
        """A scraper_done event with an error marks the scraper failed."""
        mock_ids.return_value = _TEST_SCRAPER_IDS + ["upwork"]
        run = ScraperRun("test")
        run.scraper_statuses = {pid: "pending" for pid in _TEST_SCRAPER_IDS}

        _parse_stdout_line(
            run,
            (
                '##SCRAPER_EVENT## {"type":"scraper_done","id":"upwork",'
                '"jobs":0,"duration":10.0,"error":"Exit code 1","skipped":false}'
            ),
        )
        assert run.scraper_statuses["upwork"] == "failed"
        assert run.error_message is not None

    def test_parse_stdout_line_unknown_line(self):
        """Non-event log lines should be ignored (no status changes)."""
        run = ScraperRun("test")
        run.scraper_statuses = {pid: "pending" for pid in _TEST_SCRAPER_IDS}

        _parse_stdout_line(run, "[run] Setting up scrapers...")
        _parse_stdout_line(run, "Error: something failed")
        # Should not change any statuses and not set an error from free text.
        assert all(v == "pending" for v in run.scraper_statuses.values())
        assert run.error_message is None
        assert run.issues == []

    def test_parse_stdout_line_issue_event(self):
        """An issue event is collected with severity/source/message."""
        run = ScraperRun("test")
        _parse_stdout_line(
            run,
            '##SCRAPER_EVENT## {"type":"issue","severity":"error",'
            '"source":"justjoin_it","message":"HTTP 403 from API"}',
        )
        assert len(run.issues) == 1
        issue = run.issues[0]
        assert issue["severity"] == "error"
        assert issue["source"] == "justjoin_it"
        assert issue["message"] == "HTTP 403 from API"

    def test_parse_stdout_line_unparseable_event_records_issue(self):
        """A corrupt event payload must be recorded as an issue, not dropped."""
        run = ScraperRun("test")
        _parse_stdout_line(run, "##SCRAPER_EVENT## {not valid json")
        assert len(run.issues) == 1
        assert run.issues[0]["severity"] == "warning"
        assert "Unparseable" in run.issues[0]["message"]

    @patch("job_engine.scraper_runner.get_scraper_ids")
    def test_parse_stdout_line_unknown_id_records_issue(self, mock_ids):
        """An event for an unregistered scraper id is recorded as an issue."""
        mock_ids.return_value = _TEST_SCRAPER_IDS
        run = ScraperRun("test")
        _parse_stdout_line(run, '##SCRAPER_EVENT## {"type":"scraper_start","id":"ghost"}')
        assert len(run.issues) == 1
        assert "unknown scraper id" in run.issues[0]["message"]

    @patch("job_engine.scraper_runner.get_scraper_ids")
    def test_parse_stdout_line_error_records_issue(self, mock_ids):
        """A scraper_done error event also lands in the issues list."""
        mock_ids.return_value = _TEST_SCRAPER_IDS + ["upwork"]
        run = ScraperRun("test")
        run.scraper_statuses = {"upwork": "running"}
        _parse_stdout_line(
            run,
            '##SCRAPER_EVENT## {"type":"scraper_done","id":"upwork",'
            '"jobs":0,"duration":10.0,"error":"Exit code 1","skipped":false}',
        )
        assert any(i["severity"] == "error" and i["source"] == "upwork" for i in run.issues)

    def test_get_run_logs_in_memory(self):
        """Logs for an in-memory run are served with offset-based tailing."""
        run = ScraperRun("logtest")
        run.add_log("stdout", "line one")
        run.add_log("stderr", "line two")
        run.add_issue("error", "boom", source="runner")
        # Register via TaskManager so get_run_logs can find it
        tm = get_task_manager()
        task = Task("logtest", "scraper_run", "test")
        task.metadata["scraper_run"] = run
        tm._tasks["logtest"] = task

        result = self.manager.get_run_logs("logtest")
        assert result["total_lines"] == 2
        assert [entry["line"] for entry in result["lines"]] == ["line one", "line two"]
        assert result["issues"][0]["message"] == "boom"
        assert result["live"] is True  # status defaults to running

        tail = self.manager.get_run_logs("logtest", offset=result["next_offset"])
        assert tail["lines"] == []
        assert tail["next_offset"] == result["next_offset"]

    def test_get_run_logs_unknown_run_raises(self):
        """Unknown run_id raises KeyError (no empty-response fallback)."""
        with (
            patch("job_engine.scraper_runner.config") as mock_config,
            patch("job_engine.scraper_runner.get_sync_engine"),
            patch("job_engine.scraper_runner.Session") as mock_session_cls,
        ):
            mock_config.scraper_output_dir = Path("/nonexistent-dir")
            session = mock_session_cls.return_value.__enter__.return_value
            session.execute.return_value.scalars.return_value.first.return_value = None
            with pytest.raises(KeyError):
                self.manager.get_run_logs("nope")

    @patch("job_engine.scraper_runner.save_jobs_sync")
    def test_seed_results_no_file(self, mock_save):
        """A missing _all.json is a failure, not a silently 'completed' run."""
        run = ScraperRun("test")
        run.status = "running"

        with patch("job_engine.scraper_runner.config") as mock_config:
            mock_config.all_json_path = Path("/nonexistent/_all.json")
            asyncio.run(_seed_results(run))

        mock_save.assert_not_called()
        assert run.status == "failed"
        assert "not found" in run.error_message
        assert any(i["severity"] == "error" for i in run.issues)

    @patch("job_engine.scraper_runner.save_jobs_sync")
    def test_seed_results_skipped_for_timed_out_run(self, mock_save):
        """A timed-out run must keep its status and never seed output."""
        run = ScraperRun("test")
        run.status = "timed_out"

        with patch("job_engine.scraper_runner.config") as mock_config:
            mock_config.all_json_path = Path("/nonexistent/_all.json")
            asyncio.run(_seed_results(run))

        mock_save.assert_not_called()
        assert run.status == "timed_out"
        assert any(i["severity"] == "warning" for i in run.issues)

    @patch("job_engine.scraper_runner.save_jobs_sync")
    def test_seed_results_stale_file_fails(self, mock_save, tmp_path=None):
        """An _all.json written before the run started must not be seeded."""
        import os
        import time

        run = ScraperRun("test")
        run.status = "running"

        stale_path = Path("/tmp/_all_stale_test.json")
        with open(stale_path, "w") as f:
            json.dump([], f)
        # Backdate the file well before run.started_at
        past = time.time() - 3600
        os.utime(stale_path, (past, past))

        try:
            with patch("job_engine.scraper_runner.config") as mock_config:
                mock_config.all_json_path = stale_path
                asyncio.run(_seed_results(run))
        finally:
            stale_path.unlink(missing_ok=True)

        mock_save.assert_not_called()
        assert run.status == "failed"
        assert "stale" in run.error_message

    @patch("job_engine.scraper_runner.save_jobs_sync")
    def test_seed_results_valid_json(self, mock_save):
        """With valid _all.json, seed should call save_jobs_sync."""
        mock_save.return_value = 5

        run = ScraperRun("test")
        run.status = "running"
        jobs = [{"external_id": "test1"}, {"external_id": "test2"}]

        with patch("job_engine.scraper_runner.config") as mock_config:
            mock_config.all_json_path = Path("/tmp/_all_test.json")

            # Write test data
            with open("/tmp/_all_test.json", "w") as f:
                json.dump(jobs, f)

            try:
                asyncio.run(_seed_results(run))
            finally:
                # Cleanup
                import os

                try:
                    os.remove("/tmp/_all_test.json")
                except OSError:
                    pass

        mock_save.assert_called_once_with(jobs)
        assert run.jobs_new_seeded == 5


class TestScraperRunManagerSingleton:
    """Tests for the get_scraper_manager singleton."""

    def test_singleton_returns_instance(self):
        manager = get_scraper_manager()
        assert isinstance(manager, ScraperRunManager)

    def test_singleton_is_same_instance(self):
        manager1 = get_scraper_manager()
        manager2 = get_scraper_manager()
        assert manager1 is manager2
