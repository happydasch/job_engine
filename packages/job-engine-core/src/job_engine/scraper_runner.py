import asyncio
import json
import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Any

from ruamel.yaml import YAML
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from job_engine.config import config
from job_engine.database import get_sync_engine, log_scraper_run_sync, save_jobs_sync
from job_engine.models import ScraperLog
from job_engine.scraper_config import get_scraper_config, get_scraper_ids
from job_engine.task_manager import Task, get_task_manager

logger = logging.getLogger(__name__)

# Round-trip YAML loader shared by the temp-config writer.
_yaml = YAML()
_yaml.preserve_quotes = True
_yaml.indent(mapping=2, sequence=4, offset=2)

# Marker prefix for structured events emitted by scrapers/run.js. Must match
# EVENT_MARKER in run.js.
_EVENT_MARKER = "##SCRAPER_EVENT##"

# ---------------------------------------------------------------------------
# State models
# ---------------------------------------------------------------------------


class ScraperRun:
    """In-memory state for a single scraper run."""

    def __init__(self, run_id: str):
        self.run_id: str = run_id
        self.status: str = "running"  # running | completed | failed | timed_out
        self.started_at: datetime = datetime.now(UTC)
        self.completed_at: datetime | None = None
        self.error_message: str | None = None
        self.jobs_found_total: int = 0
        self.jobs_new_seeded: int = 0
        self.scrapers_total: int = 0
        self.scrapers_completed: int = 0
        self.scraper_statuses: dict[str, str] = {}  # scraper_id -> pending/running/completed/failed
        self.scraper_job_counts: dict[str, int] = {}  # scraper_id -> job count from summary
        self.log_lines: list[dict[str, str]] = []  # {"ts", "stream", "line"}
        self.issues: list[dict[str, str | None]] = []  # {"ts", "severity", "source", "message"}
        self._process: asyncio.subprocess.Process | None = None
        self._cancelled: bool = False

    def add_log(self, stream: str, line: str) -> None:
        """Append a timestamped log line (stream: stdout | stderr | system)."""
        self.log_lines.append({"ts": datetime.now(UTC).isoformat(), "stream": stream, "line": line})

    def add_issue(self, severity: str, message: str, source: str | None = None) -> None:
        """Record a structured issue (severity: warning | error)."""
        self.issues.append(
            {
                "ts": datetime.now(UTC).isoformat(),
                "severity": severity,
                "source": source,
                "message": message,
            }
        )

    def _synthetic_done(self, pid: str, error: str) -> None:
        """Record that a scraper never reported completion
        (process ended before run.js emitted the event).

        Called during finalization when the Node.js process ended or was killed
        before run.js could emit the scraper_done event. Creates a warning so the
        dashboard shows the scraper as accounted-for rather than silently lost.
        """
        self.scraper_job_counts[pid] = self.scraper_job_counts.get(pid, 0)
        self.add_issue(
            "warning", f"Scraper never reported completion (synthetic done) [{error}]", source=pid
        )

    @property
    def elapsed_seconds(self) -> float:
        end = self.completed_at or datetime.now(UTC)
        return (end - self.started_at).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task_id": self.run_id,  # unified task_id alias
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "error_message": self.error_message,
            "jobs_found_total": self.jobs_found_total,
            "jobs_new_seeded": self.jobs_new_seeded,
            "scrapers_total": self.scrapers_total,
            "scrapers_completed": self.scrapers_completed,
            "scraper_statuses": dict(self.scraper_statuses),
            "scraper_job_counts": dict(self.scraper_job_counts),
            "issues": list(self.issues),
            "log_line_count": len(self.log_lines),
        }


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# TaskManager runner — bridges the scraper domain logic into the unified
# TaskManager so both scrapers and LLM tasks are tracked the same way.
# ---------------------------------------------------------------------------


async def _run_scraper_task(
    task: Task,
    scraper_ids: list[str],
    temp_config_path: str,
) -> None:
    """Runner function invoked by ``TaskManager.start("scraper_run", ...)``.

    Creates a ``ScraperRun``, spawns the Node.js subprocess, monitors output,
    seeds results, and persists logs — exactly the same logic that was in
    ``ScraperRunManager._spawn`` / ``_wait_and_finalize``, but now driven by
    the unified ``TaskManager`` so that any consumer can poll the same task_id.
    """
    run = ScraperRun(task.task_id)
    run.scrapers_total = len(scraper_ids)
    task.metadata["scraper_run"] = run  # link for legacy lookup

    manager = get_scraper_manager()

    # Mirror log lines onto the unified Task as well (stream-agnostic for
    # the generic task-log endpoint).
    _original_add_log = run.add_log

    def _patched_add_log(stream: str, line: str) -> None:
        _original_add_log(stream, line)
        task.add_log(f"[{stream}] {line}")

    run.add_log = _patched_add_log  # type: ignore[method-assign]

    # ---- subprocess spawning (same logic as old _spawn) ----
    script_path = config.project_root / "packages" / "job-engine-scrapers" / "run.js"
    if not script_path.exists():
        raise FileNotFoundError(f"Scraper script not found: {script_path}")

    timeout_ms = int(os.environ.get("SCRAPER_TIMEOUT_MS", "600000"))
    env = dict(os.environ)
    if temp_config_path:
        env["SCRAPER_CONFIG_PATH"] = temp_config_path

    process = await asyncio.create_subprocess_exec(
        "node",
        str(script_path),
        cwd=str(config.project_root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    run._process = process

    async def _monitor_stdout() -> None:
        assert process.stdout is not None
        while True:
            line = await process.stdout.readline()
            if not line:
                break
            decoded = line.decode("utf-8", errors="replace").rstrip()
            run.add_log("stdout", decoded)
            _parse_stdout_line(run, decoded)

    async def _monitor_stderr() -> None:
        assert process.stderr is not None
        while True:
            line = await process.stderr.readline()
            if not line:
                break
            decoded = line.decode("utf-8", errors="replace").rstrip()
            run.add_log("stderr", decoded)

    async def _finalize_body() -> None:
        monitor_stdout = asyncio.create_task(_monitor_stdout())
        monitor_stderr = asyncio.create_task(_monitor_stderr())

        try:
            exit_code = await asyncio.wait_for(process.wait(), timeout=timeout_ms / 1000.0)
        except TimeoutError:
            process.kill()
            exit_code = -1
            try:
                await process.wait()
            except ProcessLookupError:
                # Process already exited — nothing to clean up
                pass
            run.status = "timed_out"
            run.error_message = f"Scraper timed out after {timeout_ms / 1000:.0f}s"
            run.add_issue("error", run.error_message, source="runner")
        finally:
            results = await asyncio.gather(monitor_stdout, monitor_stderr, return_exceptions=True)
            for name, res in zip(("stdout monitor", "stderr monitor"), results):
                if isinstance(res, BaseException):
                    logger.error("Run %s: %s crashed", run.run_id, name, exc_info=res)
                    run.add_issue("error", f"{name} crashed: {res}", source="runner")

        if run._cancelled:
            run.status = "failed"
            if not run.error_message:
                run.error_message = "Run cancelled by shutdown"

        if run.status == "running" and exit_code != 0:
            run.status = "failed"
            run.error_message = run.error_message or f"Process exited with code {exit_code}"
            run.add_issue("error", f"Process exited with code {exit_code}", source="runner")

        await _seed_results(run)

        run.completed_at = datetime.now(UTC)

        if run.status == "running" and exit_code == 0:
            run.status = "completed"

        stale_statuses = {"pending", "running"}
        stale = [pid for pid, s in run.scraper_statuses.items() if s in stale_statuses]
        for pid in stale:
            run._synthetic_done(pid=pid, error="Timed out / process ended before completion")
            run.scraper_statuses[pid] = "failed"
            run.scrapers_completed += 1
        if stale:
            run.add_issue(
                "error",
                f"Scrapers never reported completion: {', '.join(stale)}",
                source="runner",
            )

    # Mirror the run state back to the unified Task when done
    async def _wait_and_finalize() -> None:
        try:
            await _finalize_body()
        except Exception as e:
            logger.exception("Run %s: finalization failed", run.run_id)
            run.status = "failed"
            run.error_message = run.error_message or f"Finalization failed: {e}"
            run.add_issue("error", f"Finalization failed: {e}", source="runner")
            if run.completed_at is None:
                run.completed_at = datetime.now(UTC)
        finally:
            try:
                await asyncio.to_thread(_log_to_db, run)
            except Exception as e:
                # Never let _log_to_db silently erase a run.  If persistence
                # fails (database error, disk full, etc.) we surface the
                # error on the run so it does NOT vanish from history.
                logger.exception("Run %s: _log_to_db failed", run.run_id)
                run.add_issue("error", f"Failed to persist run: {e}", source="runner")
                if run.error_message is None:
                    run.error_message = f"Persistence failed: {e}"
                # Give _log_to_db one more shot at the JSONL file only –
                # skip the DB call since it already failed.
                _log_jsonl_only(run)
            finally:
                manager._cleanup_temp_config()

            # Sync status back to the unified Task
            if run.status in ("completed", "failed", "timed_out"):
                task.status = run.status
                task.completed_at = run.completed_at
                task.error_message = run.error_message
                task.result = run.to_dict()

    await _wait_and_finalize()


# Standalone helpers extracted from ScraperRunManager so the runner can use them.


def _parse_stdout_line(run: ScraperRun, line: str) -> None:
    """Parse a structured event line emitted by run.js.

    Consuming events (rather than scraping human log text / emoji summary
    lines) means each scraper is counted exactly once and the dashboard no
    longer breaks when log formatting changes.
    """
    idx = line.find(_EVENT_MARKER)
    if idx == -1:
        return

    payload = line[idx + len(_EVENT_MARKER) :].strip()
    try:
        event = json.loads(payload)
    except (json.JSONDecodeError, ValueError) as e:
        run.add_issue("warning", f"Unparseable scraper event ({e}): {payload[:300]}")
        return

    etype = event.get("type")

    if etype == "issue":
        severity = event.get("severity") or "error"
        run.add_issue(severity, str(event.get("message", "")), source=event.get("source"))
        return

    pid = event.get("id")
    if pid not in get_scraper_ids():
        run.add_issue("warning", f"Event for unknown scraper id '{pid}': {payload[:300]}")
        return
    if etype == "scraper_start":
        run.scraper_statuses[pid] = "running"
        return

    if etype == "scraper_done":
        if run.scraper_statuses.get(pid) in ("completed", "failed", "skipped"):
            return

        jobs_count = int(event.get("jobs", 0) or 0)
        run.scraper_job_counts[pid] = jobs_count
        run.jobs_found_total += jobs_count

        if event.get("skipped"):
            run.scraper_statuses[pid] = "skipped"
            run.scrapers_completed += 1
            run.add_issue("warning", "Scraper skipped", source=pid)
        elif event.get("error"):
            run.scraper_statuses[pid] = "failed"
            run.error_message = run.error_message or str(event["error"])[:200]
            run.add_issue("error", str(event["error"]), source=pid)
        else:
            run.scraper_statuses[pid] = "completed"
            run.scrapers_completed += 1


async def _seed_results(run: ScraperRun) -> None:
    """Read _all.json and seed results into the database.

    No fallbacks: a missing/corrupt output file or a seed failure marks
    the run failed and records an issue.
    """
    all_json_path = config.all_json_path

    if run._cancelled or run.status not in ("running", "completed"):
        run.add_issue("warning", f"Seeding skipped (run status: {run.status})", source="seed")
        return

    def _fail(message: str) -> None:
        run.status = "failed"
        run.error_message = run.error_message or message
        run.add_issue("error", message, source="seed")
        logger.error("Run %s: %s", run.run_id, message)

    if not all_json_path.exists():
        _fail(f"Output file not found: {all_json_path}")
        return

    mtime = datetime.fromtimestamp(all_json_path.stat().st_mtime, tz=UTC)
    if mtime < run.started_at:
        _fail(f"Output file is stale (written before this run): {all_json_path}")
        return

    try:
        with open(all_json_path) as f:
            jobs = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        _fail(f"Failed to read _all.json: {e}")
        return

    if not isinstance(jobs, list):
        _fail(f"Invalid _all.json: expected list, got {type(jobs).__name__}")
        run.jobs_new_seeded = 0
        return

    run.jobs_found_total = max(run.jobs_found_total, len(jobs))

    try:
        new_count = await asyncio.to_thread(save_jobs_sync, jobs)
        run.jobs_new_seeded = new_count
    except Exception as e:
        logger.exception("Failed to seed jobs for run %s", run.run_id)
        _fail(f"Failed to seed jobs: {e}")


def _log_jsonl_only(run: ScraperRun) -> None:
    """Fallback when _log_to_db fails: write just the JSONL log file to disk.

    This is a best-effort persistence so the run logs are not completely lost
    even if the database write fails.  The caller should have already recorded
    the error message on the run before calling this.
    """
    try:
        output_dir = config.scraper_output_dir
        log_path = output_dir / "logs" / f"{run.run_id}.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8") as fh:
            for entry in run.log_lines:
                fh.write(json.dumps(entry) + "\n")
        logger.info("Run %s: JSONL log saved (DB persistence failed)", run.run_id)
    except Exception as e:
        logger.exception("Run %s: _log_jsonl_only also failed: %s", run.run_id, e)


def _log_to_db(run: ScraperRun) -> None:
    """Persist the run: full log to a JSONL file, outcome + issues to ScraperLog."""
    output_dir = config.scraper_output_dir
    log_path = output_dir / "logs" / f"{run.run_id}.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as fh:
        for entry in run.log_lines:
            fh.write(json.dumps(entry) + "\n")
    log_file = str(log_path)

    scraper = f"dashboard_run_{run.run_id}"
    status_map = {
        "completed": "success",
        "failed": "failed",
        "timed_out": "failed",
    }
    log_status = status_map.get(run.status, run.status)

    details = {
        "run_id": run.run_id,
        "scraper_statuses": run.scraper_statuses,
        "scraper_job_counts": dict(run.scraper_job_counts),
        "jobs_new_seeded": run.jobs_new_seeded,
        "scrapers_completed": run.scrapers_completed,
        "scrapers_total": run.scrapers_total,
        "issues": list(run.issues),
        "log_file": log_file,
        "log_line_count": len(run.log_lines),
    }

    engine = get_sync_engine()
    per_scraper_status = {
        "completed": "success",
        "failed": "failed",
        "skipped": "skipped",
    }
    for pid, pstatus in run.scraper_statuses.items():
        if pstatus in per_scraper_status:
            jobs_for_scraper = run.scraper_job_counts.get(pid, 0)
            log_scraper_run_sync(
                scraper=pid,
                jobs_found=jobs_for_scraper,
                status=per_scraper_status[pstatus],
                error_message=run.error_message if pstatus == "failed" else None,
                duration_seconds=run.elapsed_seconds,
                details=details,
                engine=engine,
            )

    log_scraper_run_sync(
        scraper=scraper,
        jobs_found=run.jobs_found_total,
        status=log_status,
        error_message=run.error_message,
        duration_seconds=run.elapsed_seconds,
        details=details,
        engine=engine,
    )


async def _noop_runner(task: Task) -> None:
    """Runner that does nothing — used when no scrapers are enabled."""
    task.status = "completed"
    task.completed_at = datetime.now(UTC)
    task.result = {"message": "No scrapers enabled, nothing to run"}


class ScraperRunManager:
    """Singleton manager for dashboard-controlled scraper runs.

    Delegates lifecycle to the unified ``TaskManager`` so that both scraper
    runs and LLM tasks are tracked the same way.  The domain-specific state
    (per-scraper statuses, job counts, issues) is stored in
    ``Task.metadata["scraper_run"]``.
    """

    def __init__(self) -> None:
        self._temp_config_path: str | None = None

    # ---- Public API ----

    async def start_run(self, scraper_ids: list[str] | None = None) -> str:
        """Spawn a new scraper run in the background.

        By default uses ``get_scraper_config().get_active_ids()`` to determine
        which scrapers to run.  Pass *scraper_ids* to run specific scrapers
        regardless of their enabled/disabled state.

        Returns the unified task_id (UUID string).
        Raises ``RuntimeError`` if a run is already in progress.
        """
        tm = get_task_manager()

        # Check for conflict via TaskManager
        active = tm.get_active("scraper_run")
        if active is not None:
            raise RuntimeError(f"A scraper run ({active.task_id}) is already in progress")

        # Determine which scrapers to run
        if scraper_ids is not None:
            active_ids = scraper_ids
        else:
            active_ids = get_scraper_config().get_active_ids()

        # If no scrapers to run, create a completed task with an error
        if not active_ids:
            task_id = await tm.start(
                "scraper_run",
                "Scraper Run (no scrapers enabled)",
                _noop_runner,
                metadata={"no_active": True, "message": "No scrapers are enabled"},
            )
            task = tm.get(task_id)
            assert task is not None
            task.status = "completed"
            task.completed_at = datetime.now(UTC)
            task.error_message = "No scrapers are enabled"
            return task_id

        # Write a temporary scraper_config.yaml
        self._cleanup_temp_config()
        temp_path = self._write_temp_config(active_ids)
        self._temp_config_path = temp_path

        # Register with the unified TaskManager.  The runner does the rest.
        label = f"Scraper Run ({', '.join(active_ids[:3])}"
        if len(active_ids) > 3:
            label += f" +{len(active_ids) - 3} more"
        label += ")"

        task_id = await tm.start(
            "scraper_run",
            label,
            lambda t: _run_scraper_task(t, active_ids, temp_path),
            metadata={"scraper_ids": active_ids, "scrapers_total": len(active_ids)},
        )

        return task_id

    def _write_temp_config(self, active_ids: list[str]) -> str:
        """Write a temporary scraper_config.yaml with only active scrapers enabled.

        The temp file is created in the project's scraper output directory
        so it's available to the Node.js subprocess. Returns the path string.

        Uses ruamel round-trip so comments/formatting are preserved, and does
        NOT mutate the original scraper_config.yaml file.

        Raises FileNotFoundError if scraper_config.yaml is missing — running
        against the original (unfiltered) config would silently ignore the
        requested scraper selection.
        """
        yaml_path = config.project_root / "data" / "scraper_config.yaml"
        if not yaml_path.exists():
            # Auto-create with all known scrapers enabled (covers the
            # single-scraper run path, which skips get_active_ids()).
            get_scraper_config().ensure_config_file()
        if not yaml_path.exists():
            raise FileNotFoundError(f"Scraper config not found: {yaml_path}")

        with yaml_path.open("r", encoding="utf-8") as fh:
            data = _yaml.load(fh) or {}

        active = set(active_ids)
        # "platforms" is the legacy key for scrapers in old config files.
        scrapers = data.get("scrapers") or data.get("platforms")
        if isinstance(scrapers, dict):
            for pid, block in scrapers.items():
                is_active = pid in active
                if isinstance(block, dict):
                    block["enabled"] = is_active
                else:
                    scrapers[pid] = {"enabled": is_active}

        # Write to a temp file in the output directory
        output_dir = config.scraper_output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        # Sweep leftovers before writing a new one (see _reap_stale_temp_configs).
        self._reap_stale_temp_configs(output_dir)
        temp_path = output_dir / f"_dashboard_config_{uuid.uuid4().hex[:8]}.yaml"
        with temp_path.open("w", encoding="utf-8") as fh:
            _yaml.dump(data, fh)
        return str(temp_path)

    def _cleanup_temp_config(self) -> None:
        """Remove the temporary config file if one exists."""
        if self._temp_config_path:
            try:
                os.unlink(self._temp_config_path)
            except FileNotFoundError:
                pass  # already gone — the only acceptable outcome besides removal
            except OSError:
                logger.exception("Failed to remove temp config %s", self._temp_config_path)
            self._temp_config_path = None

    def _reap_stale_temp_configs(self, output_dir, keep: str | None = None) -> None:
        """Delete orphaned ``_dashboard_config_*.yaml`` temp files.

        Only one run executes at a time, so any pre-existing temp config is a
        leftover from a run that was killed/timed-out/interrupted before
        ``_cleanup_temp_config`` ran (it only tracks the single in-memory path).
        Without this sweep they accumulate unbounded — hundreds were observed.
        """
        for f in output_dir.glob("_dashboard_config_*.yaml"):
            if keep and str(f) == keep:
                continue
            try:
                f.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                logger.exception("Failed to remove stale temp config %s", f)

    def get_run(self, run_id: str) -> ScraperRun | None:
        """Get in-memory state for a specific run via TaskManager metadata."""
        tm = get_task_manager()
        task = tm.get(run_id)
        if task is None:
            return None
        # Scraper-specific state is stored in task metadata
        run: ScraperRun | None = task.metadata.get("scraper_run")
        return run

    def get_last_run(self) -> ScraperRun | None:
        """Get the most recent run (active or completed)."""
        tm = get_task_manager()
        tasks = tm.list(task_type="scraper_run", limit=1)
        if not tasks:
            return None
        task = tasks[0]
        return task.metadata.get("scraper_run")

    async def cancel_run(self, run_id: str) -> dict[str, Any]:
        """Cancel a running scraper run by killing its subprocess.

        Returns the run's ``to_dict()`` representation.
        Raises ``ValueError`` if the run is not found or not running.
        """
        tm = get_task_manager()
        task = tm.get(run_id)
        if task is None:
            raise ValueError(f"Run {run_id} not found")

        run: ScraperRun | None = task.metadata.get("scraper_run")
        if run is None:
            raise ValueError(f"Run {run_id} has no scraper state")

        if task.status != "running":
            raise ValueError(f"Run {run_id} is not running (status: {task.status})")

        run.error_message = "Run cancelled by user"
        run._cancelled = True
        run.status = "failed"
        run.completed_at = datetime.now(UTC)
        run.add_issue("warning", "Run cancelled by user", source="runner")

        if run._process:
            try:
                run._process.kill()
                try:
                    await asyncio.wait_for(run._process.wait(), timeout=10.0)
                except (TimeoutError, ProcessLookupError):
                    pass
            except ProcessLookupError:
                pass

        # Also mark the unified task
        task.status = "failed"
        task.completed_at = run.completed_at
        task.error_message = run.error_message

        self._cleanup_temp_config()
        return run.to_dict()

    def get_active_run(self) -> ScraperRun | None:
        """Get the currently running run, if any."""
        tm = get_task_manager()
        task = tm.get_active("scraper_run")
        if task is None:
            return None
        return task.metadata.get("scraper_run")

    def get_run_history(self, limit: int = 20) -> list[dict[str, Any]]:
        """Get historical run log entries from the ScraperLog table."""
        engine = get_sync_engine()
        with Session(engine) as session:
            rows = (
                session.execute(select(ScraperLog).order_by(desc(ScraperLog.run_at)).limit(limit))
                .scalars()
                .all()
            )
            result: list[dict[str, Any]] = []
            # Group by run_id (using details JSON if available)
            groups: dict[str, dict[str, Any]] = {}
            for row in rows:
                rid = _extract_run_id(row)
                if rid not in groups:
                    # SQLite strips tzinfo on storage; re-apply UTC for naive datetimes
                    started_at = row.run_at.isoformat()
                    if row.run_at.tzinfo is None:
                        started_at += "+00:00"
                    groups[rid] = {
                        "run_id": rid,
                        "status": row.status,
                        "started_at": started_at,
                        "jobs_found": 0,
                        "jobs_new": 0,
                        "duration": row.duration_seconds,
                        "scrapers": [],
                        "scraper_statuses": {},
                        "error": row.error_message,
                        "issues_count": 0,
                    }
                # Skip dashboard_run_* entries when collecting scraper names
                if not row.scraper.startswith("dashboard_run_"):
                    groups[rid]["jobs_found"] += row.jobs_found
                    groups[rid]["scrapers"].append(row.scraper)

                # Extract jobs_new from the aggregate dashboard_run log's details
                if jobs_new_val := _extract_jobs_new(row):
                    groups[rid]["jobs_new"] = jobs_new_val

                # Extract scraper_statuses from the aggregate dashboard_run row
                _extract_scraper_statuses(row, groups[rid])

                # Use status/error from the aggregate dashboard_run row when available
                if row.scraper.startswith("dashboard_run_"):
                    groups[rid]["status"] = row.status
                    if row.error_message:
                        groups[rid]["error"] = row.error_message
                    if row.duration_seconds is not None:
                        groups[rid]["duration"] = row.duration_seconds
                    details = _parse_details(row)
                    groups[rid]["issues_count"] = len(details.get("issues") or [])

            result = list(groups.values())
            result.sort(key=lambda x: x["started_at"], reverse=True)
            return result[:limit]

    def get_run_logs(self, run_id: str, offset: int = 0) -> dict[str, Any]:
        """Return log lines + issues for a run.

        Live runs are served from memory (pass *offset* to tail incrementally);
        finished runs are read back from the persisted JSONL log file and the
        aggregate ScraperLog row. Raises KeyError for an unknown run_id.
        """
        tm = get_task_manager()
        task = tm.get(run_id)
        if task is not None:
            run: ScraperRun | None = task.metadata.get("scraper_run")
            if run is not None:
                lines = run.log_lines[offset:]
                return {
                    "run_id": run_id,
                    "status": run.status,
                    "offset": offset,
                    "next_offset": offset + len(lines),
                    "total_lines": len(run.log_lines),
                    "lines": lines,
                    "issues": list(run.issues),
                    "live": run.status == "running",
                }

        # Historical run: log file on disk + issues from the aggregate DB row.
        log_path = config.scraper_output_dir / "logs" / f"{run_id}.jsonl"
        lines = []
        if log_path.exists():
            with log_path.open("r", encoding="utf-8") as fh:
                for raw in fh:
                    raw = raw.strip()
                    if raw:
                        lines.append(json.loads(raw))

        engine = get_sync_engine()
        with Session(engine) as session:
            row = (
                session.execute(
                    select(ScraperLog)
                    .where(ScraperLog.scraper == f"dashboard_run_{run_id}")
                    .order_by(desc(ScraperLog.run_at))
                    .limit(1)
                )
                .scalars()
                .first()
            )

        if row is None and not log_path.exists():
            raise KeyError(f"Run {run_id} not found")

        status = row.status if row is not None else "unknown"
        issues: list[dict[str, Any]] = []
        if row is not None and row.details:
            issues = json.loads(row.details).get("issues") or []

        sliced = lines[offset:]
        return {
            "run_id": run_id,
            "status": status,
            "offset": offset,
            "next_offset": offset + len(sliced),
            "total_lines": len(lines),
            "lines": sliced,
            "issues": issues,
            "live": False,
        }

    # ---- Scheduler (periodic auto-run) ----

    _scheduler_task: asyncio.Task | None = None
    _scheduler_interval_minutes: int = 360  # default 6 hours
    _scheduler_enabled: bool = False

    def get_scheduler_config(self) -> dict[str, Any]:
        """Return current scheduler configuration."""
        return {
            "enabled": self._scheduler_enabled,
            "interval_minutes": self._scheduler_interval_minutes,
        }

    async def set_scheduler_config(
        self, enabled: bool | None = None, interval_minutes: int | None = None
    ) -> dict[str, Any]:
        """Update scheduler configuration and restart if running."""
        if interval_minutes is not None:
            self._scheduler_interval_minutes = max(1, interval_minutes)
        if enabled is not None:
            self._scheduler_enabled = enabled

        # Restart the scheduler
        if self._scheduler_task:
            self._scheduler_task.cancel()
            self._scheduler_task = None

        if self._scheduler_enabled:
            self._scheduler_task = asyncio.create_task(self._scheduler_loop())

        return self.get_scheduler_config()

    async def _scheduler_loop(self) -> None:
        """Background loop: wait interval, then start a run if idle."""
        # Wait a bit before first run so the server is fully ready
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            return

        while True:
            try:
                interval_seconds = self._scheduler_interval_minutes * 60
                await asyncio.sleep(interval_seconds)
                if self._scheduler_enabled and not self.get_active_run():
                    await self.start_run()
            except asyncio.CancelledError:
                break
            except (OSError, RuntimeError, ValueError):
                # Never let a single failed auto-run kill the scheduler, but do
                # surface it — silently swallowing made failures invisible.
                logger.exception("Scheduled scraper run failed; will retry next interval")

    async def shutdown(self) -> None:
        """Cancel any active run, kill its subprocess, and stop the scheduler."""
        # Stop the scheduler
        if self._scheduler_task:
            self._scheduler_task.cancel()
            self._scheduler_task = None

        active = self.get_active_run()
        if active and active._process:
            active._cancelled = True
            try:
                active._process.kill()
                await active._process.wait()
            except ProcessLookupError:
                # Process already exited — nothing to clean up
                pass

        # Shut down the unified TaskManager
        tm = get_task_manager()
        await tm.shutdown()


def _parse_details(row: ScraperLog) -> dict[str, Any]:
    """Parse a ScraperLog row's details JSON.

    Corrupt details are a data problem — logged loudly, never silently
    ignored — but must not take down the whole history endpoint, so the
    row degrades to an empty dict.
    """
    if not row.details:
        return {}
    try:
        parsed = json.loads(row.details)
    except (json.JSONDecodeError, TypeError):
        logger.error("ScraperLog row %s has corrupt details JSON", row.id, exc_info=True)
        return {}
    if not isinstance(parsed, dict):
        logger.error(
            "ScraperLog row %s details is not an object (type=%s)", row.id, type(parsed).__name__
        )
        return {}
    return parsed


def _extract_run_id(row: ScraperLog) -> str:
    """Extract a run grouping ID from a ScraperLog row.

    Uses the details JSON's run_id if available, otherwise the scraper name.
    """
    return _parse_details(row).get("run_id") or row.scraper


def _extract_jobs_new(row: ScraperLog) -> int | None:
    """Extract jobs_new_seeded from a ScraperLog row's details JSON, if available."""
    val = _parse_details(row).get("jobs_new_seeded")
    return int(val) if val is not None else None


def _extract_scraper_statuses(row: ScraperLog, group: dict[str, Any]) -> None:
    """Extract scraper_statuses from a ScraperLog row's details JSON into the group dict."""
    parsed = _parse_details(row)
    # "platform_statuses" is the legacy key in details JSON persisted by older runs.
    statuses = parsed.get("scraper_statuses") or parsed.get("platform_statuses")
    if statuses and isinstance(statuses, dict):
        for pid, pstatus in statuses.items():
            group.setdefault("scraper_statuses", {})[pid] = pstatus


# ---------------------------------------------------------------------------
# Module-level singleton (same lazy-init pattern as _matcher in api/main)
# ---------------------------------------------------------------------------

_manager: ScraperRunManager | None = None


def get_scraper_manager() -> ScraperRunManager:
    """Lazy-init and return the global scraper run manager singleton."""
    global _manager
    if _manager is None:
        _manager = ScraperRunManager()
    return _manager
