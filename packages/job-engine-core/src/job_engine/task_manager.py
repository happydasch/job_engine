"""
TaskManager — single runner for ALL background work in the Job Engine.

Both scrapers and LLM operations register their tasks here.  Any component can
call :meth:`TaskManager.start` to fire off a background task, then poll
:meth:`TaskManager.get` for status, logs, and the final result.

Usage::

    tm = get_task_manager()
    task_id = await tm.start("llm_analysis", "Analyze job X", runner_coro,
                             metadata={"job_id": "..."})
    task = tm.get(task_id)
    if task and task.status == "completed":
        print(task.result)
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# Retain completed tasks for this many seconds before evicting them from memory.
_RETENTION_SECONDS = 300  # 5 minutes


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


class Task:
    """In-memory state for a single background task."""

    def __init__(self, task_id: str, task_type: str, label: str) -> None:
        self.task_id: str = task_id
        self.task_type: str = task_type  # e.g. "scraper_run", "llm_analysis"
        self.label: str = label
        self.status: str = "running"  # running | completed | failed
        self.started_at: datetime = datetime.now(UTC)
        self.completed_at: datetime | None = None
        self.result: Any | None = None  # JSON-serializable final result
        self.error_message: str | None = None
        self.progress_pct: float | None = None  # 0.0-100.0
        self.metadata: dict[str, Any] = {}  # domain-specific payload
        self.log_lines: list[dict[str, str]] = []  # [{"ts": ..., "line": ...}]
        self._cancel_requested: bool = False

    def add_log(self, line: str) -> None:
        """Append a timestamped log line."""
        self.log_lines.append({"ts": datetime.now(UTC).isoformat(), "line": line})

    @property
    def elapsed_seconds(self) -> float:
        end = self.completed_at or datetime.now(UTC)
        return (end - self.started_at).total_seconds()

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "label": self.label,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "elapsed_seconds": round(self.elapsed_seconds, 1),
            "result": self.result,
            "error_message": self.error_message,
            "progress_pct": self.progress_pct,
            "metadata": dict(self.metadata),
            "log_line_count": len(self.log_lines),
        }


# Type alias for a runner: an async callable that receives the Task as first arg.
Runner = Callable[[Task], Coroutine[None, None, None]]


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------


class TaskManager:
    """Singleton manager for all fire-and-forget background tasks."""

    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}
        self._lock: asyncio.Lock = asyncio.Lock()

    # ---- Public API ----

    async def start(
        self,
        task_type: str,
        label: str,
        runner: Runner,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Start a background task and return its task_id immediately.

        *runner* is an async callable ``async def runner(task: Task)`` that
        receives the created Task and should update its status / result as it
        progresses.  The runner is spawned via ``asyncio.create_task``; any
        unhandled exception inside the runner is caught and recorded on the task.
        """
        task_id = uuid.uuid4().hex[:12]
        task = Task(task_id, task_type, label)
        if metadata:
            task.metadata = metadata

        async with self._lock:
            self._tasks[task_id] = task

        # Spawn the runner — never wait for it here.
        asyncio.create_task(self._run(task, runner))

        return task_id

    def get(self, task_id: str) -> Task | None:
        """Retrieve a task by ID, or *None* if unknown."""
        return self._tasks.get(task_id)

    def list(
        self,
        task_type: str | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> list[Task]:
        """List tasks, optionally filtered by type/status, newest first."""
        results = [
            t
            for t in self._tasks.values()
            if (task_type is None or t.task_type == task_type)
            and (status is None or t.status == status)
        ]
        results.sort(key=lambda t: t.started_at, reverse=True)
        return results[:limit]

    def get_active(self, task_type: str | None = None) -> Task | None:
        """Return the currently running task, optionally filtered by type."""
        for task in self._tasks.values():
            if task.status == "running":
                if task_type is None or task.task_type == task_type:
                    return task
        return None

    def cancel(self, task_id: str) -> dict[str, Any]:
        """Request cancellation of a running task.

        The runner is responsible for checking ``task._cancel_requested`` and
        cleaning up.  Returns the task's ``to_dict()`` representation.

        Raises ``ValueError`` if the task is not found or not running.
        """
        task = self._tasks.get(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        if task.status != "running":
            raise ValueError(f"Task {task_id} is not running (status: {task.status})")

        task._cancel_requested = True
        task.error_message = "Cancelled by user"
        # The runner will pick this up and finalise.
        return task.to_dict()

    def get_logs(self, task_id: str, offset: int = 0) -> dict[str, Any]:
        """Return log lines for a task (offset-based pagination)."""
        task = self._tasks.get(task_id)
        if task is None:
            raise KeyError(f"Task {task_id} not found")

        lines = task.log_lines[offset:]
        return {
            "task_id": task_id,
            "status": task.status,
            "offset": offset,
            "next_offset": offset + len(lines),
            "total_lines": len(task.log_lines),
            "lines": lines,
        }

    async def shutdown(self) -> None:
        """Cancel all running tasks and clear completed ones."""
        async with self._lock:
            for task in list(self._tasks.values()):
                if task.status == "running":
                    task._cancel_requested = True
                    task.status = "failed"
                    task.error_message = "Shutdown"
                    task.completed_at = datetime.now(UTC)
            self._tasks.clear()

    # ---- Internal ----

    async def _run(self, task: Task, runner: Runner) -> None:
        """Wrap *runner* execution: catch exceptions, evict stale tasks later."""
        try:
            await runner(task)
        except asyncio.CancelledError:
            task.status = "failed"
            task.error_message = task.error_message or "Task cancelled"
        except Exception as exc:
            logger.exception("Task %s (%s) failed", task.task_id, task.label)
            task.status = "failed"
            task.error_message = task.error_message or str(exc)
            task.add_log(f"ERROR: {exc}")
        finally:
            if task.status == "running":
                task.status = "completed"
            if task.completed_at is None:
                task.completed_at = datetime.now(UTC)

        # Schedule eviction of this completed task from memory after retention.
        asyncio.create_task(self._evict_later(task.task_id))

    async def _evict_later(self, task_id: str) -> None:
        """Remove a completed/failed task from memory after retention period."""
        await asyncio.sleep(_RETENTION_SECONDS)
        self._tasks.pop(task_id, None)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_manager: TaskManager | None = None


def get_task_manager() -> TaskManager:
    """Lazy-init and return the global TaskManager singleton."""
    global _manager
    if _manager is None:
        _manager = TaskManager()
    return _manager
