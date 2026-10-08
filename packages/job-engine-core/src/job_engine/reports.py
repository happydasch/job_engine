"""Numbered sequential reports for LLM analysis output.

Reports are stored in data/reports/ with monotonically increasing numbers.
Format: {report_number}.json
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from job_engine.config import config as _config

logger = logging.getLogger(__name__)

_REPORTS_DIR = _config.data_dir / "reports"


def _get_reports_dir() -> Path:
    """Ensure the reports directory exists and return its path."""
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return _REPORTS_DIR


def _get_counter_path() -> Path:
    """Return the path to the counter file."""
    return _get_reports_dir() / "_counter.txt"


def _read_counter() -> int:
    """Read the current counter value, or 0 if not set."""
    counter_path = _get_counter_path()
    if counter_path.exists():
        try:
            return int(counter_path.read_text().strip())
        except (ValueError, OSError):
            logger.warning("Corrupt report counter, resetting to 0")
    return 0


def _write_counter(value: int) -> None:
    """Write the counter value atomically."""
    counter_path = _get_counter_path()
    counter_path.write_text(str(value))


def allocate_number() -> int:
    """Allocate the next sequential report number.

    Thread-safe for single-process usage. For multi-process safety,
    use file locking.

    Returns:
        The next available report number (1-based).
    """
    current = _read_counter()
    next_num = current + 1
    _write_counter(next_num)
    return next_num


def save_report(job_id: int, analysis_data: dict[str, Any]) -> str:
    """Save an analysis report to data/reports/.

    Args:
        job_id: The job ID being analyzed.
        analysis_data: The analysis data dict.

    Returns:
        The path to the saved report file as a string.
    """
    report_number = allocate_number()
    report = {
        "report_number": report_number,
        "job_id": job_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": {
            "key_skills": analysis_data.get("key_skills", []),
            "seniority": analysis_data.get("seniority", ""),
            "match_score": analysis_data.get("match_score", None),
            "red_flags": analysis_data.get("red_flags", []),
        },
        "analysis": analysis_data,
    }

    reports_dir = _get_reports_dir()
    report_path = reports_dir / f"{report_number}.json"

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)

    logger.info("Saved report #%d for job %d to %s", report_number, job_id, report_path)
    return str(report_path)


def get_report(path: str | Path) -> dict[str, Any] | None:
    """Load a report from a file path.

    Args:
        path: Path to the report JSON file.

    Returns:
        The report dict, or None if not found or invalid.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Report not found: {path}")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to load report %s: %s", path, e)
        raise


def get_report_by_number(number: int) -> dict[str, Any] | None:
    """Load a report by its sequential number.

    Args:
        number: The report number (1-based).

    Returns:
        The report dict, or None if not found.
    """
    return get_report(_get_reports_dir() / f"{number}.json")


def get_reports_for_job(job_id: int) -> list[dict[str, Any]]:
    """Get all reports for a specific job.

    Args:
        job_id: The job ID to search for.

    Returns:
        List of report dicts for the job.
    """
    reports_dir = _get_reports_dir()
    results = []
    for f in sorted(reports_dir.glob("*.json"), key=lambda p: p.name):
        if f.name == "_counter.txt":
            continue
        report = get_report(f)
        if report and report.get("job_id") == job_id:
            results.append(report)
    return results
